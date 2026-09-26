"""Sensors for mOdpady schedules."""

from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import ModpadyCoordinator


DESCRIPTIONS = (
    SensorEntityDescription(
        key="next_collection",
        translation_key="next_collection",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-arrow-right",
    ),
    SensorEntityDescription(
        key="next_collection_types",
        translation_key="next_collection_types",
        icon="mdi:trash-can-outline",
    ),
    SensorEntityDescription(
        key="upcoming_collections",
        translation_key="upcoming_collections",
        icon="mdi:calendar-multiple",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="days_until_collection",
        translation_key="days_until_collection",
        icon="mdi:calendar-clock",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="collection_by_type",
        translation_key="collection_by_type",
        icon="mdi:trash-can-clock",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


def _icon_for_waste_type(waste_type: str) -> str:
    normalized_type = waste_type.casefold()
    icon_by_keywords = (
        (("szkło", "szklo", "glass"), "mdi:bottle-soda"),
        (("papier", "paper", "tektura", "cardboard"), "mdi:newspaper-variant-outline"),
        (("plastik", "tworzyw", "plastic", "metal"), "mdi:recycle"),
        (("bio", "biodegrad", "kuchenn", "organic"), "mdi:leaf"),
        (("gabaryt", "bulky"), "mdi:sofa"),
        (("elektro", "electrical", "bater", "battery"), "mdi:lightning-bolt"),
        (("niebezpiecz", "hazard", "chemic", "lek", "medical"), "mdi:flask-outline"),
        (("popio", "ash"), "mdi:fire"),
        (("zielon", "gałęz", "galaz", "branch", "garden"), "mdi:tree"),
    )
    return next(
        (
            icon
            for keywords, icon in icon_by_keywords
            if any(keyword in normalized_type for keyword in keywords)
        ),
        "mdi:trash-can",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ModpadyCoordinator = entry.runtime_data
    async_add_entities(
        ModpadySensor(coordinator, entry, description)
        for description in DESCRIPTIONS
        if description.key != "collection_by_type"
    )

    known_waste_types = {
        waste_type
        for item in coordinator.data.get("schedule", [])
        for waste_type in item.get("waste_types", [])
    }
    waste_type_description = next(
        item for item in DESCRIPTIONS if item.key == "collection_by_type"
    )
    async_add_entities(
        ModpadySensor(coordinator, entry, waste_type_description, waste_type)
        for waste_type in sorted(known_waste_types)
    )

    def _add_new_waste_type_sensors() -> None:
        new_waste_types = {
            waste_type
            for item in coordinator.data.get("schedule", [])
            for waste_type in item.get("waste_types", [])
        } - known_waste_types
        if not new_waste_types:
            return
        known_waste_types.update(new_waste_types)
        async_add_entities(
            ModpadySensor(coordinator, entry, waste_type_description, waste_type)
            for waste_type in sorted(new_waste_types)
        )

    entry.async_on_unload(coordinator.async_add_listener(_add_new_waste_type_sensors))


class ModpadySensor(CoordinatorEntity[ModpadyCoordinator], SensorEntity):
    """Represent one property of the configured collection schedule."""

    entity_description: SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ModpadyCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        waste_type: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.waste_type = waste_type
        suffix = f"_{waste_type}" if waste_type else ""
        self._attr_unique_id = f"{entry.entry_id}_{description.key}{suffix}"
        if waste_type:
            self._attr_icon = _icon_for_waste_type(waste_type)
            self._attr_translation_placeholders = {"waste_type": waste_type}
        settings = coordinator.settings
        street = settings.get("street_name")
        address_label = " ".join(
            part
            for part in (
                settings.get("locality_name", settings["locality_id"]),
                street,
                settings["address"],
            )
            if part
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=address_label,
            manufacturer="mOdpady",
            model=settings.get("city_name", settings["city"]),
        )

    @property
    def native_value(self):
        schedule = self.coordinator.data.get("schedule", [])
        key = self.entity_description.key
        if key == "next_collection":
            return date.fromisoformat(schedule[0]["date"]) if schedule else None
        if key == "next_collection_types":
            return ", ".join(schedule[0]["waste_types"]) if schedule else None
        if key == "upcoming_collections":
            return len(schedule)
        if key == "days_until_collection":
            return (date.fromisoformat(schedule[0]["date"]) - dt_util.now().date()).days if schedule else None
        if key == "collection_by_type" and self.waste_type:
            matching_dates = [
                date.fromisoformat(item["date"])
                for item in schedule
                if self.waste_type in item.get("waste_types", [])
            ]
            return (min(matching_dates) - dt_util.now().date()).days if matching_dates else None
        return None

    @property
    def extra_state_attributes(self) -> dict:
        settings = self.coordinator.settings
        attributes = {
            "city": settings.get("city_name", settings["city"]),
            "locality": settings.get("locality_name", settings["locality_id"]),
            "street": settings.get("street_name") or None,
            "address": settings["address"],
        }
        if self.entity_description.key in ("next_collection", "next_collection_types"):
            attributes["upcoming_schedule"] = self.coordinator.data.get("schedule", [])
        if self.entity_description.key == "collection_by_type" and self.waste_type:
            attributes["waste_type"] = self.waste_type
            attributes["next_collection"] = self.native_value_date
        return attributes

    @property
    def native_value_date(self) -> str | None:
        if not self.waste_type:
            return None
        for item in self.coordinator.data.get("schedule", []):
            if self.waste_type in item.get("waste_types", []):
                return item["date"]
        return None

