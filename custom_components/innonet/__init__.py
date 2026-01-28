"""Initialisierung der INNOnet Integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import InnonetDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Liste der unterstützen Plattformen
# Wir binden Sensor (für Preise/Daten) und Binary Sensor (für Signale) ein
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einrichten der Integration über einen Config Entry."""
    _LOGGER.debug("Richte INNOnet Integration ein: %s", entry.title)

    # Erstelle den DataUpdateCoordinator
    # Dieser übernimmt ab jetzt das stündliche Update (10s nach Punkt) 
    # sowie den Nullwert-Schutz.
    coordinator = InnonetDataUpdateCoordinator(hass, entry)
    
    # Speichere den Coordinator in hass.data, damit Sensoren darauf zugreifen können
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Leite das Setup an die Plattformen weiter
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entfernen eines Config Entries (z.B. beim Löschen oder Deaktivieren)."""
    # Entlade alle registrierten Plattformen
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Hole den Coordinator aus dem Speicher
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Wichtig: Beende den Timer im Coordinator, damit keine Hintergrund-Updates mehr laufen
        await coordinator.async_close()

    return unload_ok