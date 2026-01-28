"""Sensor Plattform für INNOnet."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import (
    DOMAIN, 
    PRICE_COMPONENT_BASE, 
    PRICE_COMPONENT_FEE, 
    PRICE_COMPONENT_VAT,
    PRICE_COMPONENT_ENERGY_PREFIX,
    CONF_TOTAL_PRICE_NAME,
    NAME_MAPPING
)

async def async_setup_entry(hass, entry, async_add_entities):
    """Sensoren anlegen."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Sicherstellen, dass Daten vorhanden sind, bevor Entitäten erstellt werden
    if coordinator.data is None:
        await coordinator.async_config_entry_first_refresh()

    entities = []
    if coordinator.data:
        for storage_key, info in coordinator.data.items():
            # Nur Preis-relevante oder gewünschte Sensoren als SensorEntity
            # Signale werden im binary_sensor.py behandelt
            if "tariff-signal" not in info["name"]:
                entities.append(InnoNetSensor(coordinator, storage_key, info, entry))
    
    entities.append(InnoNetTotalPriceSensor(coordinator, entry))
    async_add_entities(entities)

class InnoNetSensor(CoordinatorEntity, SensorEntity):
    """Einzelner Sensor aus der API mit Namens-Mapping."""

    def __init__(self, coordinator, storage_key, info, entry):
        super().__init__(coordinator)
        self._storage_key = storage_key
        
        # Namens-Mapping anwenden
        internal_name = info["name"]
        display_name = internal_name
        for pattern, replacement in NAME_MAPPING.items():
            if internal_name.startswith(pattern) or internal_name == pattern:
                display_name = replacement
                break
        
        self._attr_name = display_name
        self._attr_unique_id = f"innonet_s_{info['id']}_{entry.entry_id}"
        self._attr_native_unit_of_measurement = info["unit"]
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="INNOnet",
            manufacturer="INNOnet",
            model="Tarif-API",
        )
        
        unit = str(info["unit"])
        if "EUR" in unit or "Cent" in unit:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_state_class = None # Fix für Warnung: measurement nicht erlaubt für monetary
        elif "kWh" in unit:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        data = self.coordinator.data.get(self._storage_key)
        return data["value"] if data else None

class InnoNetTotalPriceSensor(CoordinatorEntity, SensorEntity):
    """Berechnet den Total Price."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_name = CONF_TOTAL_PRICE_NAME
        self._attr_unique_id = f"innonet_total_price_{entry.entry_id}"
        self._attr_native_unit_of_measurement = "EUR/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="INNOnet",
            manufacturer="INNOnet",
            model="Tarif-API",
        )

    @property
    def native_value(self):
        total = 0.0
        found = False
        if not self.coordinator.data:
            return None

        for item in self.coordinator.data.values():
            name = item["name"]
            if (name.startswith(PRICE_COMPONENT_ENERGY_PREFIX) or 
                name in [PRICE_COMPONENT_BASE, PRICE_COMPONENT_FEE, PRICE_COMPONENT_VAT]):
                val = float(item["value"])
                if "Cent" in str(item["unit"]):
                    total += val / 100.0
                else:
                    total += val
                found = True
        
        return round(total, 4) if found else None