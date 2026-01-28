"""Binary Sensor Plattform für INNOnet."""
import logging
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, SIGNAL_TARIFF

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Binary Sensoren anlegen."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    if coordinator.data is None:
        await coordinator.async_config_entry_first_refresh()
    
    entities = []
    if coordinator.data:
        for storage_key, info in coordinator.data.items():
            # Wir nutzen das Tarif-Signal für den Status des Sonnenfensters
            if info["name"].startswith(SIGNAL_TARIFF):
                entities.append(InnoNetSunActiveSensor(coordinator, storage_key, entry))
            
    async_add_entities(entities)

class InnoNetSunActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Repräsentiert binary_sensor.innonet_service_sun_window_active."""
    def __init__(self, coordinator, storage_key, entry):
        super().__init__(coordinator)
        self._storage_key = storage_key
        # Exaktes ID Schema wie gewünscht
        self.entity_id = "binary_sensor.innonet_service_sun_window_active"
        self._attr_name = "Sun Window Active"
        self._attr_unique_id = f"innonet_sun_act_{entry.entry_id}"
        self._attr_device_class = BinarySensorDeviceClass.POWER
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="INNOnet",
            manufacturer="INNOnet",
            model="Service API",
        )

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data: return False
        data = self.coordinator.data.get(self._storage_key)
        if not data: return False
        try:
            return float(data["value"]) >= 1.0
        except (ValueError, TypeError):
            return False