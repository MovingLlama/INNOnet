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
from homeassistant.util import dt as dt_util

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
        InnonetGridPriceSensor(coordinator, entry),
        InnonetEnergyPriceSensor(coordinator, entry),
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


class InnonetGridPriceSensor(InnonetBaseSensor):
    """Sensor for Grid Price (Netzkosten)."""
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_grid_price"
        self._attr_name = "Grid Price"
        self._attr_icon = "mdi:transmission-tower"
        self._attr_native_unit_of_measurement = "EUR/kWh"
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data.get("grid_price")
        # Coordinator auto-converts Cent/kWh to EUR/kWh
        if data and "v" in data:
            return data["v"]
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, any]:
        return self.coordinator.data.get("grid_price", {})


class InnonetEnergyPriceSensor(InnonetBaseSensor):
    """Sensor for Energy Price (Energiekosten) incl. VAT."""
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_energy_price"
        self._attr_name = "Energy Price"
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_native_unit_of_measurement = "EUR/kWh"
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data.get("energy_price")
        if data and "v" in data:
            val = data["v"]
            # Add 20% VAT to get the Gross price (e.g. 0.1545 -> 0.1854)
            try:
                return round(float(val) * 1.2, 5)
            except (ValueError, TypeError):
                return val
        return None

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        return self.coordinator.data.get("energy_price", {})


class InnonetTariffSignalSensor(InnonetBaseSensor):
    """Text Sensor for Signal."""
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_tariff_signal"
        self._attr_name = "Tariff Signal"
        self._attr_icon = "mdi:traffic-light"
        self._attr_options = ["Standard", "Sonnenfenster (Low)", "Unknown"]
        self._attr_device_class = SensorDeviceClass.ENUM

    @property
    def native_value(self) -> str | None:
        item = self.coordinator.data.get("tariff_signal_now")
        if not item: return None
        val = item.get("v")
        
        try:
            if val is not None:
                val = int(float(val))
        except (ValueError, TypeError):
            pass 
        
        if val == 0: return "Standard"
        if val == 1: return "Sonnenfenster (Low)"
        return "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        return self.coordinator.data.get("tariff_signal_now", {})


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
        val = self.coordinator.data.get("next_sun_start")
        if val:
            return dt_util.parse_datetime(val)
        return None


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
        val = self.coordinator.data.get("next_sun_end")
        if val:
            return dt_util.parse_datetime(val)
        return None