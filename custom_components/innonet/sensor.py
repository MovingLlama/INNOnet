"""Sensor Plattform für INNOnet."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN, 
    PRICE_COMPONENT_BASE, 
    PRICE_COMPONENT_FEE, 
    PRICE_COMPONENT_VAT,
    CONF_TOTAL_PRICE_NAME
)

async def async_setup_entry(hass, entry, async_add_entities):
    """Sensoren anlegen."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    entities = []
    
    # API Sensoren hinzufügen
    for storage_key, info in coordinator.data.items():
        entities.append(InnoNetSensor(coordinator, storage_key, info))
    
    # Berechneten Gesamtsensor für den Preis hinzufügen
    entities.append(InnoNetTotalPriceSensor(coordinator, entry))
    
    async_add_entities(entities)

class InnoNetSensor(CoordinatorEntity, SensorEntity):
    """Einzelner Sensor aus der API."""

    def __init__(self, coordinator, storage_key, info):
        super().__init__(coordinator)
        self._storage_key = storage_key
        self._attr_name = info["name"]
        self._attr_unique_id = f"innonet_{info['id']}"
        self._attr_native_unit_of_measurement = info["unit"]
        
        unit = str(info["unit"])
        if "EUR" in unit or "Cent" in unit:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif "kWh" in unit:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        data = self.coordinator.data.get(self._storage_key)
        return data["value"] if data else None

class InnoNetTotalPriceSensor(CoordinatorEntity, SensorEntity):
    """Berechnet die Summe der Preiskomponenten."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_name = CONF_TOTAL_PRICE_NAME
        self._attr_unique_id = f"innonet_total_price_{entry.entry_id}"
        self._attr_native_unit_of_measurement = "EUR/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Summiert Basis, Fee und Vat mit Einheitenkorrektur."""
        total = 0.0
        found = False
        
        for item in self.coordinator.data.values():
            if item["name"] in [PRICE_COMPONENT_BASE, PRICE_COMPONENT_FEE, PRICE_COMPONENT_VAT]:
                val = float(item["value"])
                # Korrektur: Cent/kWh -> EUR/kWh
                if "Cent" in str(item["unit"]):
                    total += val / 100.0
                else:
                    total += val
                found = True
        
        return round(total, 4) if found else None