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
    """Sensoren basierend auf dem Config Entry anlegen."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Warte auf den ersten Datenabruf, falls noch keine Daten da sind
    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    entities = []
    
    # 1. Erstelle individuelle Sensoren für jeden API-Eintrag
    for storage_key, info in coordinator.data.items():
        entities.append(InnoNetSensor(coordinator, storage_key, info))
    
    # 2. Erstelle den berechneten Gesamtsensor (Addition der Preiskomponenten)
    entities.append(InnoNetTotalPriceSensor(coordinator, entry))
    
    async_add_entities(entities)

class InnoNetSensor(CoordinatorEntity, SensorEntity):
    """Repräsentation eines INNOnet Sensors."""

    def __init__(self, coordinator, storage_key, info):
        """Initialisierung."""
        super().__init__(coordinator)
        self._storage_key = storage_key
        self._attr_name = info["name"]
        self._attr_unique_id = f"innonet_{info['id']}"
        self._attr_native_unit_of_measurement = info["unit"]
        
        # Automatische Klassifizierung für Energie- und Geldwerte
        unit = str(info["unit"])
        if "EUR" in unit or "Cent" in unit:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif "kWh" in unit:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        """Gibt den aktuellen Wert aus dem Coordinator zurück."""
        data = self.coordinator.data.get(self._storage_key)
        if data:
            return data["value"]
        return None

    @property
    def extra_state_attributes(self):
        """Zusätzliche Attribute."""
        data = self.coordinator.data.get(self._storage_key)
        if data:
            return {
                "api_id": data["id"],
                "internal_name": data["name"]
            }
        return {}

class InnoNetTotalPriceSensor(CoordinatorEntity, SensorEntity):
    """Berechnet den Gesamtpreis aus Basis, Gebühr und Steuer."""

    def __init__(self, coordinator, entry):
        """Initialisierung des Summen-Sensors."""
        super().__init__(coordinator)
        self._attr_name = CONF_TOTAL_PRICE_NAME
        self._attr_unique_id = f"innonet_total_price_{entry.entry_id}"
        self._attr_native_unit_of_measurement = "EUR/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Berechnet die Summe der Preiskomponenten inkl. Einheiten-Korrektur."""
        total = 0.0
        found_any = False
        
        # Wir gehen alle Daten durch und suchen die in const.py definierten Namen
        for item in self.coordinator.data.values():
            name = item.get("name")
            val = item.get("value")
            unit = item.get("unit", "")
            
            if val is None:
                continue

            # Überprüfung gegen die Preiskomponenten-Liste
            if name in [PRICE_COMPONENT_BASE, PRICE_COMPONENT_FEE, PRICE_COMPONENT_VAT]:
                # Umrechnung von Cent in EUR falls nötig
                if "Cent" in str(unit):
                    total += float(val) / 100.0
                else:
                    total += float(val)
                found_any = True
        
        if not found_any:
            return None
            
        return round(total, 4)