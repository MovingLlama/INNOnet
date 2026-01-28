"""Sensor Plattform für INNOnet."""
from datetime import datetime
import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN, 
    PRICE_COMPONENT_BASE, 
    PRICE_COMPONENT_FEE, 
    PRICE_COMPONENT_VAT,
    PRICE_COMPONENT_ENERGY_PREFIX,
    SIGNAL_TARIFF
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Sensoren anlegen."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    if coordinator.data is None:
        await coordinator.async_config_entry_first_refresh()

    entities = [
        InnoNetTotalPriceSensor(coordinator, entry),
        InnoNetSunWindowTimeSensor(coordinator, entry, "start"),
        InnoNetSunWindowTimeSensor(coordinator, entry, "end")
    ]
    
    if coordinator.data:
        for storage_key, info in coordinator.data.items():
            name = info["name"]
            # Filter: Keine Signale und keine validierten Daten
            if name.startswith(SIGNAL_TARIFF) or name.startswith("validated-data"):
                continue
                
            entities.append(InnoNetServiceSensor(coordinator, storage_key, info, entry))
    
    async_add_entities(entities)

class InnoNetBaseEntity(CoordinatorEntity):
    """Basis-Klasse für die Geräte-Gruppierung."""
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        # Identische DeviceInfo für alle Entitäten erzwingt die Gruppierung als ein Gerät
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="INNOnet",
            manufacturer="INNOnet",
            model="Service API",
            configuration_url="https://app-innonnetwebtsm-dev.azurewebsites.net/",
        )

class InnoNetServiceSensor(InnoNetBaseEntity, SensorEntity):
    """Sensoren für Einzelpreise (Energy, Grid, etc.)."""
    def __init__(self, coordinator, storage_key, info, entry):
        super().__init__(coordinator, entry)
        self._storage_key = storage_key
        
        raw_name = info["name"]
        slug = raw_name.replace("public-energy-", "").replace("innonet-", "").replace("-", "_").lower()
        self.entity_id = f"sensor.innonet_service_{slug}"
        self._attr_name = raw_name.replace("-", " ").title()
        self._attr_unique_id = f"innonet_s_{info['id']}_{entry.entry_id}"
        
        unit = str(info["unit"])
        if "EUR" in unit or "Cent" in unit:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = unit
            # 'total' erlaubt Langzeitstatistiken für Währungswerte ohne Fehler
            self._attr_state_class = SensorStateClass.TOTAL
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
        # Ermöglicht Statistiken für den Gesamtpreis
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        total = 0.0
        found = False
        for item in self.coordinator.data.values():
            name = item["name"]
            if (name.startswith(PRICE_COMPONENT_ENERGY_PREFIX) or 
                name in [PRICE_COMPONENT_BASE, PRICE_COMPONENT_FEE, PRICE_COMPONENT_VAT]):
                try:
                    val = float(item["value"])
                    total += (val / 100.0) if "Cent" in str(item["unit"]) else val
                    found = True
                except (ValueError, TypeError):
                    continue
        return round(total, 4) if found else None

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
        for item in self.coordinator.data.values():
            if item["name"].startswith(SIGNAL_TARIFF):
                series = item.get("time_series", [])
                for point in series:
                    try:
                        val = float(point.get("Value", 0))
                        if (self._mode == "start" and val >= 1.0) or (self._mode == "end" and val < 1.0):
                            from_time = point.get("From")
                            if from_time:
                                return datetime.fromisoformat(from_time.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue
        return None