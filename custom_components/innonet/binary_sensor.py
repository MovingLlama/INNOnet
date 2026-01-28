"""Binary Sensor Plattform für INNOnet."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import CONF_API_KEY
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Binary Sensoren anlegen."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Wir suchen nach dem Signal-Sensor in den Coordinator-Daten
    for storage_key, info in coordinator.data.items():
        if "tariff-signal" in info["name"]:
            entities.append(InnoNetSignalBinarySensor(coordinator, storage_key, info, entry))
            
    async_add_entities(entities)

class InnoNetSignalBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Repräsentiert ein Signal (z.B. Tarif-Fenster aktiv) als Binary Sensor."""

    def __init__(self, coordinator, storage_key, info, entry):
        super().__init__(coordinator)
        self._storage_key = storage_key
        self._attr_name = f"Signal {info['name']}"
        # Nutze Entry-ID statt dem fehlenden 'zpn' Feld
        self._attr_unique_id = f"innonet_signal_{info['id']}_{entry.entry_id}"
        self._attr_device_class = BinarySensorDeviceClass.PLUG

    @property
    def is_on(self) -> bool:
        """Gibt True zurück, wenn das Signal 1 ist."""
        data = self.coordinator.data.get(self._storage_key)
        if data:
            return float(data["value"]) >= 1.0
        return False