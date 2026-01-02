"""Sensor platform for INNOnet."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_TARIFF_SIGNAL, SENSOR_INNONET_TARIFF
from .coordinator import InnonetDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up INNOnet sensors."""
    coordinator: InnonetDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        InnonetTariffSignalSensor(coordinator, entry),
        InnonetTariffPriceSensor(coordinator, entry),
    ]

    # Add 24 Forecast Sensors (1h to 24h)
    for hour_offset in range(1, 25):
        entities.append(InnonetPriceForecastSensor(coordinator, entry, hour_offset))

    async_add_entities(entities)


class InnonetBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for INNOnet sensors."""

    def __init__(
        self, coordinator: InnonetDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["zpn"])},
            name="INNOnet Service",
            manufacturer="INNOnet",
            configuration_url="https://www.ait.ac.at/themen/flexibilitaet-geschaeftsmodelle/projekte/projekt-innonet",
        )


class InnonetTariffSignalSensor(InnonetBaseSensor):
    """Sensor for the Tariff Signal (0, 1, -1)."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_tariff_signal"
        self._attr_name = "Tariff Signal"
        self._attr_icon = "mdi:traffic-light"
        self._attr_options = ["Project Tariff", "High Tariff", "Low Tariff (Sun)", "Unknown"]
        self._attr_device_class = SensorDeviceClass.ENUM

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        data = self.coordinator.data.get("tariff_signal")
        if not data:
            return None
        
        # Signal values: 0, 1, -1. Expecting 'v' after normalization.
        val = data.get("v")
        
        if val == 0:
            return "Project Tariff" # Projekttarif
        elif val == 1:
            return "High Tariff" # Hochtarif
        elif val == -1:
            return "Low Tariff (Sun)" # Niedertarif (Sonnenfenster)
        
        return "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return raw value in attributes for automation logic."""
        data = self.coordinator.data.get("tariff_signal")
        if not data:
            return {}
        return {
            "raw_value": data.get("v"),
            "timestamp": data.get("t"),
            "flag": data.get("f")
        }


class InnonetTariffPriceSensor(InnonetBaseSensor):
    """Sensor for the current INNOnet Tariff Price."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_innonet_price"
        self._attr_name = "Tariff Price"
        self._attr_icon = "mdi:currency-eur"
        self._attr_native_unit_of_measurement = "EUR/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        data = self.coordinator.data.get("innonet_tariff")
        if not data:
            return None
        return data.get("v")


class InnonetPriceForecastSensor(InnonetBaseSensor):
    """Sensor for INNOnet Tariff Price Forecast (+X hours)."""

    def __init__(self, coordinator, entry, hour_offset: int):
        super().__init__(coordinator, entry)
        self.hour_offset = hour_offset
        # Unique ID distinguishes the hours: e.g. ..._price_forecast_1h
        self._attr_unique_id = f"{entry.data['zpn']}_price_forecast_{hour_offset}h"
        self._attr_name = f"Price +{hour_offset}h"
        self._attr_icon = "mdi:clock-time-three-outline"
        self._attr_native_unit_of_measurement = "EUR/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_value(self) -> float | None:
        """Return the forecast value from the list."""
        forecast_list = self.coordinator.data.get("price_forecast")
        if not forecast_list:
            return None
        
        # forecast_list contains 24 items (usually).
        # Index 0 is +1h (since we queried from now[1h) IF we consider "now" as index -1?
        # Actually API query: from=now[1h to=now[1h+24h.
        # This returns 24 values starting with the *next* full hour (or current full hour).
        # Let's assume index 0 is +0h (current hour average) or +1h depending on 'from'.
        # 'now[1h' rounds to the START of the current hour usually.
        # So index 0 is "Current Hour", index 1 is "+1h".
        
        # If the user wants +1h, we might need index 1.
        # Let's map it safely.
        if len(forecast_list) > self.hour_offset:
             # If index 0 is current hour, then index 'hour_offset' is +X hours away.
             item = forecast_list[self.hour_offset]
             return item.get("v")
        
        return None
        
    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Show timestamp of this forecast slot."""
        forecast_list = self.coordinator.data.get("price_forecast")
        if forecast_list and len(forecast_list) > self.hour_offset:
            item = forecast_list[self.hour_offset]
            return {
                "forecast_time": item.get("t"),
                "flag": item.get("f")
            }
        return {}