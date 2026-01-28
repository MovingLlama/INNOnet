"""Button Plattform für INNOnet."""
from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Button Entität anlegen."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Füge den Aktualisierungs-Button hinzu
    async_add_entities([InnoNetUpdateButton(coordinator, entry)])

class InnoNetUpdateButton(CoordinatorEntity, ButtonEntity):
    """Button zum manuellen Aktualisieren der Daten."""

    def __init__(self, coordinator, entry):
        """Initialisierung des Buttons."""
        super().__init__(coordinator)
        self._entry = entry
        
        # Schema-konforme Benennung
        self.entity_id = "button.innonet_service_update"
        self._attr_name = "Update Now"
        self._attr_unique_id = f"innonet_update_btn_{entry.entry_id}"
        self._attr_device_class = ButtonDeviceClass.UPDATE
        
        # Gruppierung im gleichen Gerät "INNOnet"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="INNOnet",
            manufacturer="INNOnet",
            model="Service API",
            configuration_url="https://app-innonnetwebtsm-dev.azurewebsites.net/",
        )

    async def async_press(self) -> None:
        """Wird ausgeführt, wenn der Button gedrückt wird."""
        # Triggert den Coordinator sofort
        await self.coordinator.async_request_refresh()