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
        
        # Signal values: 0, 1, -1
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
            "flag": data.get("f") # Data quality flag
        }


class InnonetTariffPriceSensor(InnonetBaseSensor):
    """Sensor for the INNOnet Tariff Price."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data['zpn']}_innonet_price"
        self._attr_name = "Tariff Price"
        self._attr_icon = "mdi:currency-eur"
        self._attr_native_unit_of_measurement = "EUR/kWh" # Assuming EUR based on context
        self._attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        data = self.coordinator.data.get("innonet_tariff")
        if not data:
            return None
        
        # Check flags for missing values (Flag 19 mentioned in docs)
        # However, we simply return the 'v' (value) if present.
        return data.get("v")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # If the API returns valid structure but no price data (e.g. only signal),
        # this sensor might be temporarily unavailable or just showing None.
        return super().available