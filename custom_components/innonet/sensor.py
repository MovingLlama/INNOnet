"""Sensor Plattform für INNOnet."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import CONF_API_KEY
from .const import (
    DOMAIN, 
    PRICE_COMPONENT_BASE, 
    PRICE_COMPONENT_FEE, 
    PRICE_COMPONENT_VAT,
    PRICE_COMPONENT_ENERGY_PREFIX,
    SIGNAL_TARIFF
)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Sicherstellen, dass Daten da sind
    if coordinator.data is None:
        await coordinator.async_config_entry_first_refresh()

    entities = [
        InnoNetTotalPriceSensor(coordinator, entry),
        InnoNetSunWindowTimeSensor(coordinator, entry, "start"),
        InnoNetSunWindowTimeSensor(coordinator, entry, "end")
    ]
    
    # Dynamische Sensoren für Einzelpreise
    if coordinator.data:
        for storage_key, info in coordinator.data.items():
            if not info["name"].startswith(SIGNAL_TARIFF):
                entities.append(InnoNetServiceSensor(coordinator, storage_key, info, entry))
    
    async_add_entities(entities)

class InnoNetBaseEntity(CoordinatorEntity):
    """Basis-Klasse für INNOnet Gerät-Gruppierung."""
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="INNOnet",
            manufacturer="INNOnet",
            model="Service API",
        )

class InnoNetServiceSensor(InnoNetBaseEntity, SensorEntity):
    """Standard Sensoren mit innonnet_service Schema."""
    def __init__(self, coordinator, storage_key, info, entry):
        super().__init__(coordinator, entry)
        self._storage_key = storage_key
        
        # ID-Schema Mapping
        raw_name = info["name"]
        slug = raw_name.replace("public-energy-", "").replace("innonet-", "").replace("-", "_").lower()
        self.entity_id = f"sensor.innonet_service_{slug}"
        self._attr_name = raw_name.replace("-", " ").title()
        self._attr_unique_id = f"innonet_s_{info['id']}_{entry.entry_id}"
        
        unit = str(info["unit"])
        if "EUR" in unit or "Cent" in unit:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = unit
        elif "kWh" in unit:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        return self.coordinator.data.get(self._storage_key, {}).get("value")

class InnoNetTotalPriceSensor(InnoNetBaseEntity, SensorEntity):
    """Berechnet sensor.innonet_service_total_price."""
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self.entity_id = "sensor.innonet_service_total_price"
        self._attr_name = "Total Price"
        self._attr_unique_id = f"innonet_total_p_{entry.entry_id}"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "EUR/kWh"

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        total = 0.0
        for item in self.coordinator.data.values():
            name = item["name"]
            if (name.startswith(PRICE_COMPONENT_ENERGY_PREFIX) or 
                name in [PRICE_COMPONENT_BASE, PRICE_COMPONENT_FEE, PRICE_COMPONENT_VAT]):
                val = float(item["value"])
                total += (val / 100.0) if "Cent" in str(item["unit"]) else val
        return round(total, 4)

class InnoNetSunWindowTimeSensor(InnoNetBaseEntity, SensorEntity):
    """Nächstes Sonnenfenster Start/Ende."""
    def __init__(self, coordinator, entry, mode):
        super().__init__(coordinator, entry)
        self._mode = mode
        self.entity_id = f"sensor.innonet_service_next_sun_window_{mode}"
        self._attr_name = f"Next Sun Window {mode.title()}"
        self._attr_unique_id = f"innonet_sun_{mode}_{entry.entry_id}"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        # Suche nach dem tariff-signal item
        for item in self.coordinator.data.values():
            if item["name"].startswith(SIGNAL_TARIFF):
                series = item.get("time_series", [])
                # Logik zur Erkennung des nächsten Wechsels (vereinfacht)
                for point in series:
                    val = float(point.get("Value", 0))
                    if (self._mode == "start" and val >= 1.0) or (self._mode == "end" and val < 1.0):
                        return datetime.fromisoformat(point["From"].replace("Z", "+00:00"))
        return None