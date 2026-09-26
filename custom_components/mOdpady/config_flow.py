"""Config and options flows for mOdpady."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .api import (
    ModpadyApiError,
    async_get_addresses,
    async_get_cities,
    async_get_localities,
    async_get_streets,
)
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _select(options: list[dict[str, str]]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _options(items: list[dict], *, id_key: str = "id") -> list[dict[str, str]]:
    return [
        {
            "value": str(item[id_key]),
            "label": str(item.get("extendedName") or item.get("name") or item[id_key]),
        }
        for item in items
    ]


class ModpadyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a city address through successive dropdowns."""

    VERSION = 1

    def __init__(self) -> None:
        self.selection: dict[str, str] = {}

    async def async_step_user(self, user_input=None):
        return await self.async_step_city(user_input)

    async def async_step_city(self, user_input=None):
        errors = {}
        try:
            cities = await async_get_cities(self.hass)
        except ModpadyApiError:
            cities = []
            errors["base"] = "cannot_connect"
        if not cities and not errors:
            errors["base"] = "no_deployments"

        if user_input is not None:
            selected = next(
                (city for city in cities if city["value"] == user_input["city"]), None
            )
            if selected is None:
                errors["base"] = "invalid_selection"
            else:
                self.selection["city"] = selected["value"]
                self.selection["city_name"] = selected["label"].rsplit(" (", 1)[0]
                return await self.async_step_locality()

        return self.async_show_form(
            step_id="city",
            data_schema=vol.Schema({vol.Required("city"): _select(cities)}),
            errors=errors,
        )

    async def async_step_locality(self, user_input=None):
        errors = {}
        try:
            localities = await async_get_localities(self.hass, self.selection["city"])
        except ModpadyApiError:
            localities = []
            errors["base"] = "cannot_connect"
        if not localities and not errors:
            errors["base"] = "no_localities"

        if user_input is not None:
            locality = next(
                (item for item in localities if str(item["id"]) == user_input["locality_id"]),
                None,
            )
            if locality is None:
                errors["base"] = "invalid_selection"
            else:
                self.selection["locality_id"] = str(locality["id"])
                self.selection["locality_name"] = locality.get("extendedName") or locality["name"]
                return await self.async_step_street()

        return self.async_show_form(
            step_id="locality",
            data_schema=vol.Schema(
                {vol.Required("locality_id"): _select(_options(localities))}
            ),
            errors=errors,
            description_placeholders={"city": self.selection.get("city_name", "")},
        )

    async def async_step_street(self, user_input=None):
        errors = {}
        try:
            streets = await async_get_streets(
                self.hass, self.selection["city"], self.selection["locality_id"]
            )
        except ModpadyApiError:
            streets = []
            errors["base"] = "cannot_connect"

        if not streets and not errors:
            self.selection.update(street_id="", street_name="")
            return await self.async_step_address()

        if user_input is not None:
            street = next(
                (item for item in streets if str(item["id"]) == user_input["street_id"]),
                None,
            )
            if street is None:
                errors["base"] = "invalid_selection"
            else:
                self.selection["street_id"] = str(street["id"])
                self.selection["street_name"] = street.get("extendedName") or street["name"]
                return await self.async_step_address()

        return self.async_show_form(
            step_id="street",
            data_schema=vol.Schema({vol.Required("street_id"): _select(_options(streets))}),
            errors=errors,
        )

    async def async_step_address(self, user_input=None):
        errors = {}
        address_options = []
        if self.selection.get("street_id"):
            try:
                addresses = await async_get_addresses(
                    self.hass,
                    self.selection["city"],
                    self.selection["locality_id"],
                    self.selection["street_id"],
                )
                address_options = [
                    {"value": str(address), "label": str(address)} for address in addresses
                ]
            except ModpadyApiError:
                errors["base"] = "cannot_connect"

        if user_input is not None:
            address = user_input["address"].strip()
            if not address:
                errors["base"] = "invalid_address"
            elif address_options and address not in {item["value"] for item in address_options}:
                errors["base"] = "invalid_selection"
            else:
                self.selection["address"] = address
                await self.async_set_unique_id(
                    "_".join(
                        self.selection[key]
                        for key in ("city", "locality_id", "street_id", "address")
                    )
                )
                self._abort_if_unique_id_configured()
                self.selection["title"] = f"{self.selection['locality_name']} {address}"
                return await self.async_step_interval()

        address_schema = (
            _select(address_options)
            if address_options
            else selector.TextSelector()
        )
        return self.async_show_form(
            step_id="address",
            data_schema=vol.Schema({vol.Required("address"): address_schema}),
            errors=errors,
        )

    async def async_step_interval(self, user_input=None):
        if user_input is not None:
            self.selection["update_interval"] = int(user_input["update_interval"])
            title = self.selection.pop("title")
            return self.async_create_entry(title=title, data=self.selection)

        return self.async_show_form(
            step_id="interval",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "update_interval", default=DEFAULT_SCAN_INTERVAL
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=5,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    )
                }
            ),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return ModpadyOptionsFlow(config_entry)


class ModpadyOptionsFlow(config_entries.OptionsFlow):
    """Edit polling interval or reconfigure the selected address."""

    def __init__(self, config_entry) -> None:
        self.selection: dict[str, str] = {}
        self.update_interval = int(
            config_entry.options.get(
                "update_interval", DEFAULT_SCAN_INTERVAL
            )
        )

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self.update_interval = int(user_input["update_interval"])
            if user_input["change_address"]:
                return await self.async_step_city()
            return self.async_create_entry(
                title="",
                data={**self.config_entry.options, "update_interval": self.update_interval},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "update_interval", default=self.update_interval
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=5,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                    vol.Required("change_address", default=False): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_city(self, user_input=None):
        errors = {}
        try:
            cities = await async_get_cities(self.hass)
        except ModpadyApiError:
            cities = []
            errors["base"] = "cannot_connect"
        if not cities and not errors:
            errors["base"] = "no_deployments"

        if user_input is not None:
            selected = next(
                (city for city in cities if city["value"] == user_input["city"]), None
            )
            if selected is None:
                errors["base"] = "invalid_selection"
            else:
                self.selection["city"] = selected["value"]
                self.selection["city_name"] = selected["label"].rsplit(" (", 1)[0]
                return await self.async_step_locality()

        return self.async_show_form(
            step_id="city",
            data_schema=vol.Schema({vol.Required("city"): _select(cities)}),
            errors=errors,
        )

    async def async_step_locality(self, user_input=None):
        errors = {}
        try:
            localities = await async_get_localities(self.hass, self.selection["city"])
        except ModpadyApiError:
            localities = []
            errors["base"] = "cannot_connect"
        if not localities and not errors:
            errors["base"] = "no_localities"

        if user_input is not None:
            locality = next(
                (item for item in localities if str(item["id"]) == user_input["locality_id"]),
                None,
            )
            if locality is None:
                errors["base"] = "invalid_selection"
            else:
                self.selection["locality_id"] = str(locality["id"])
                self.selection["locality_name"] = locality.get("extendedName") or locality["name"]
                return await self.async_step_street()

        return self.async_show_form(
            step_id="locality",
            data_schema=vol.Schema(
                {vol.Required("locality_id"): _select(_options(localities))}
            ),
            errors=errors,
            description_placeholders={"city": self.selection.get("city_name", "")},
        )

    async def async_step_street(self, user_input=None):
        errors = {}
        try:
            streets = await async_get_streets(
                self.hass, self.selection["city"], self.selection["locality_id"]
            )
        except ModpadyApiError:
            streets = []
            errors["base"] = "cannot_connect"

        if not streets and not errors:
            self.selection.update(street_id="", street_name="")
            return await self.async_step_address()

        if user_input is not None:
            street = next(
                (item for item in streets if str(item["id"]) == user_input["street_id"]),
                None,
            )
            if street is None:
                errors["base"] = "invalid_selection"
            else:
                self.selection["street_id"] = str(street["id"])
                self.selection["street_name"] = street.get("extendedName") or street["name"]
                return await self.async_step_address()

        return self.async_show_form(
            step_id="street",
            data_schema=vol.Schema({vol.Required("street_id"): _select(_options(streets))}),
            errors=errors,
        )

    async def async_step_address(self, user_input=None):
        errors = {}
        address_options = []
        if self.selection.get("street_id"):
            try:
                addresses = await async_get_addresses(
                    self.hass,
                    self.selection["city"],
                    self.selection["locality_id"],
                    self.selection["street_id"],
                )
                address_options = [
                    {"value": str(address), "label": str(address)} for address in addresses
                ]
            except ModpadyApiError:
                errors["base"] = "cannot_connect"

        if user_input is not None:
            address = user_input["address"].strip()
            if not address:
                errors["base"] = "invalid_address"
            elif address_options and address not in {item["value"] for item in address_options}:
                errors["base"] = "invalid_selection"
            else:
                self.selection["address"] = address
                return self.async_create_entry(
                    title="",
                    data={
                        **self.config_entry.options,
                        **self.selection,
                        "update_interval": self.update_interval,
                    },
                )

        address_schema = _select(address_options) if address_options else selector.TextSelector()
        return self.async_show_form(
            step_id="address",
            data_schema=vol.Schema({vol.Required("address"): address_schema}),
            errors=errors,
        )

