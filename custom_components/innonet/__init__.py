"""Initialisierung der INNOnet Integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import InnonetDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Liste der unterstützen Plattformen
# Wir binden nun auch die Button-Plattform ein
PLATFORMS: list[Platform] = [
    Platform.SENSOR, 
    Platform.BINARY_SENSOR, 
    Platform.BUTTON
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einrichten der Integration über einen Config Entry."""
    _LOGGER.debug("Richte INNOnet Integration ein: %s", entry.title)

    coordinator = InnonetDataUpdateCoordinator(hass, entry)
    
    # Speichere den Coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Leite das Setup an die Plattformen weiter
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entfernen eines Config Entries."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()

    return unload_ok