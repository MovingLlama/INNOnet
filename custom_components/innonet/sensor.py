"""Sensor Plattform für INNOnet."""
from datetime import datetime
import logging

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

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
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
            if name.startswith(SIGNAL_TARIFF) or name.startswith("validated-data"):
                continue
            entities.append(InnoNetServiceSensor(coordinator, storage_key, info, entry))
    
    async_add_entities(entities)

class InnoNetBaseEntity(CoordinatorEntity):
    """Basis für alle INNOnet Entitäten."""
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
    """Sensoren für Preise mit Namens-Logik."""
    def __init__(self, coordinator, storage_key, info, entry):
        super().__init__(coordinator, entry)
        self._storage_key = storage_key
        raw_name = info["name"]
        
        # Spezielle Umbenennung für den Tariff-Sensor
        if raw_name.startswith("innonet-tariff-"):
            slug = "tariff"
            self._attr_name = "Innonet Tariff"
        else:
            slug = raw_name.replace("public-energy-", "").replace("innonet-", "").replace("-", "_").lower()
            self._attr_name = raw_name.replace("-", " ").title()
            
        self.entity_id = f"sensor.innonet_service_{slug}"
        self._attr_unique_id = f"innonet_s_{info['id']}_{entry.entry_id}"
        
        unit = str(info["unit"])
        if "EUR" in unit or "Cent" in unit:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = unit
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
    """Gesamtpreis-Sensor."""
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self.entity_id = "sensor.innonet_service_total_price"
        self._attr_name = "Total Price"
        self._attr_unique_id = f"innonet_total_p_{entry.entry_id}"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "EUR/kWh"
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
                except (ValueError, TypeError): continue
        return round(total, 4) if found else None

class InnoNetSunWindowTimeSensor(InnoNetBaseEntity, SensorEntity):
    """Optimierte Zeit-Erkennung für das Sonnenfenster."""
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
                if not series: return None
                
                current_active = float(series[0].get("Value", 0)) >= 1.0
                
                # Modus "Start": Wann beginnt das nächste (oder übernächste) Fenster?
                if self._mode == "start":
                    # Wenn aktuell inaktiv, suche das nächste >= 1
                    # Wenn aktuell aktiv, suche erst den Wechsel auf 0, dann wieder auf 1
                    found_inactive = not current_active
                    for point in series[1:]:
                        val = float(point.get("Value", 0))
                        if not found_inactive and val < 1.0:
                            found_inactive = True
                        elif found_inactive and val >= 1.0:
                            return self._parse_time(point["From"])
                            
                # Modus "Ende": Wann endet das aktuelle (oder nächste) Fenster?
                elif self._mode == "end":
                    # Wenn aktuell aktiv, suche das nächste < 1
                    # Wenn aktuell inaktiv, suche erst den Wechsel auf 1, dann wieder auf 0
                    found_active = current_active
                    for point in series[1:]:
                        val = float(point.get("Value", 0))
                        if not found_active and val >= 1.0:
                            found_active = True
                        elif found_active and val < 1.0:
                            return self._parse_time(point["From"])
        return None

    def _parse_time(self, date_str):
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception: return None