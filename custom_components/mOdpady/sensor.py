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
    )


class ModpadySensor(CoordinatorEntity[ModpadyCoordinator], SensorEntity):
    """Represent one property of the configured collection schedule."""

    entity_description: SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ModpadyCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
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
        return attributes

