"""Binary Sensor Plattform für INNOnet."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Binary Sensoren anlegen."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Fehlerprüfung: Falls Daten noch nicht geladen sind
    if coordinator.data is None:
        await coordinator.async_config_entry_first_refresh()

    entities = []
    if coordinator.data:
        for storage_key, info in coordinator.data.items():
            if "tariff-signal" in info["name"]:
                entities.append(InnoNetSignalBinarySensor(coordinator, storage_key, info, entry))
                # Sun Window Active ist meistens identisch mit dem Tariff Signal
                entities.append(InnoNetSunWindowSensor(coordinator, storage_key, entry))
            
    async_add_entities(entities)

class InnoNetSignalBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Tariff Signal."""

    def __init__(self, coordinator, storage_key, info, entry):
        super().__init__(coordinator)
        self._storage_key = storage_key
        self._attr_name = "Tariff Signal"
        self._attr_unique_id = f"innonet_bs_{info['id']}_{entry.entry_id}"
        self._attr_device_class = BinarySensorDeviceClass.PLUG
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="INNOnet",
            manufacturer="INNOnet",
            model="Tarif-API",
        )

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data: return False
        data = self.coordinator.data.get(self._storage_key)
        try:
            return float(data["value"]) >= 1.0 if data else False
        except Exception:
            return False

class InnoNetSunWindowSensor(CoordinatorEntity, BinarySensorEntity):
    """Sun Window Active."""

    def __init__(self, coordinator, storage_key, entry):
        super().__init__(coordinator)
        self._storage_key = storage_key
        self._attr_name = "Sun Window Active"
        self._attr_unique_id = f"innonet_sun_active_{entry.entry_id}"
        self._attr_device_class = BinarySensorDeviceClass.POWER
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="INNOnet",
            manufacturer="INNOnet",
            model="Tarif-API",
        )

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data: return False
        data = self.coordinator.data.get(self._storage_key)
        try:
            return float(data["value"]) >= 1.0 if data else False
        except Exception:
            return False