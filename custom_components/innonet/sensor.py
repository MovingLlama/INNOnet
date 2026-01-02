"""Sensor platform for INNOnet."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import InnonetDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up INNOnet sensors."""
    coordinator: InnonetDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        InnonetCurrentPriceSensor(coordinator, entry),
        InnonetTariffSignalSensor(coordinator, entry),
        InnonetNextSunWindowStartSensor(coordinator, entry),
        InnonetNextSunWindowEndSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class InnonetBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class."""
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["zpn"])},
            name="INNOnet Service",
            manufacturer="INNOnet",
        )


class InnonetCurrentPriceSensor(InnonetBaseSensor):
    """Sensor for current price with history tracking."""
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_current_price"
        self._attr_name = "Current Grid Price"
        self._attr_icon = "mdi:currency-eur"
        self._attr_native_unit_of_measurement = "EUR/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data.get("current_price")
        # Ensure we return 0 if the value is explicitly 0 (and not None)
        if data and "v" in data:
            return data["v"]
        return None


class InnonetTariffSignalSensor(InnonetBaseSensor):
    """Text Sensor for Signal (Project, High, Low)."""
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_tariff_signal"
        self._attr_name = "Tariff Signal"
        self._attr_icon = "mdi:traffic-light"
        self._attr_options = ["Project Tariff", "High Tariff", "Low Tariff (Sun)", "Unknown"]
        self._attr_device_class = SensorDeviceClass.ENUM

    @property
    def native_value(self) -> str | None:
        item = self.coordinator.data.get("tariff_signal_now")
        if not item: return None
        val = item.get("v")
        if val == 0: return "Project Tariff"
        if val == 1: return "High Tariff"
        if val == -1: return "Low Tariff (Sun)"
        return "Unknown"


class InnonetNextSunWindowStartSensor(InnonetBaseSensor):
    """Timestamp when the next Sun Window starts."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_sun_start"
        self._attr_name = "Next Sun Window Start"
        self._attr_icon = "mdi:clock-start"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        return self.coordinator.data.get("next_sun_start")


class InnonetNextSunWindowEndSensor(InnonetBaseSensor):
    """Timestamp when the next Sun Window ends."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_sun_end"
        self._attr_name = "Next Sun Window End"
        self._attr_icon = "mdi:clock-end"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        return self.coordinator.data.get("next_sun_end")