"""DataUpdateCoordinator für die INNOnet Integration."""
import logging
import async_timeout
import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_change
from homeassistant.const import CONF_API_KEY

from .const import DOMAIN, BASE_URL, UPDATE_OFFSET_SECONDS, UPDATE_CRON_MINUTE

_LOGGER = logging.getLogger(__name__)

class InnoNetDataUpdateCoordinator(DataUpdateCoordinator):
    """Klasse zur Verwaltung des Datenabrufs von der INNOnet API."""

    def __init__(self, hass: HomeAssistant, entry):
        """Initialisierung des Coordinators."""
        self.api_key = entry.data.get(CONF_API_KEY)
        self.entry = entry
        
        # Speicher für persistente Werte (behält letzten Wert > 0)
        self._persistent_values = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None, # Update-Intervall auf None, da wir manuell steuern
        )

        # Registriere den Timer für 10 Sekunden nach der vollen Stunde
        self._unsub_timer = async_track_time_change(
            hass,
            self._async_scheduled_update,
            minute=UPDATE_CRON_MINUTE,
            second=UPDATE_OFFSET_SECONDS
        )

    @callback
    async def _async_scheduled_update(self, _now=None):
        """Wird stündlich um :00:10 aufgerufen."""
        _LOGGER.debug("Geplante stündliche Aktualisierung wird ausgeführt")
        await self.async_refresh()

    async def _async_update_data(self):
        """Daten von der API abrufen. Wird beim Start und stündlich aufgerufen."""
        # URL mit Zeitfilter für die aktuelle Stunde
        url = f"{BASE_URL}/{self.api_key}/timeseriescollections/selected-data?from=now[30m&to=now[30m%2B1h&interval=hour"
        
        _LOGGER.debug("Rufe Daten von API ab: %s", url)

        try:
            async with async_timeout.timeout(30):
                async with aiohttp.ClientSession() as session:
                    response = await session.get(url)
                    response.raise_for_status()
                    data = await response.json()
                    return self._process_data(data)

        except Exception as err:
            _LOGGER.error("API Fehler beim Abruf: %s", err)
            raise UpdateFailed(f"Kommunikationsfehler mit INNOnet: {err}")

    def _process_data(self, raw_data):
        """Verarbeitet Daten und sichert Werte gegen 0-Einträge ab."""
        processed = {}

        for item in raw_data:
            name = item.get("Name")
            sensor_id = item.get("ID")
            storage_key = f"{name}_{sensor_id}"
            
            try:
                data_list = item.get("Data", {}).get("Data", [])
                if not data_list:
                    # Falls keine Daten kommen, versuchen wir den letzten bekannten Wert zu halten
                    val = self._persistent_values.get(storage_key, 0.0)
                else:
                    new_value = data_list[0].get("Value")
                    
                    # Nullwert-Schutz: Wenn 0, verwende den letzten gespeicherten gültigen Wert
                    if (new_value == 0 or new_value == 0.0):
                        val = self._persistent_values.get(storage_key, 0.0)
                    else:
                        self._persistent_values[storage_key] = new_value
                        val = new_value
                
                processed[storage_key] = {
                    "value": val,
                    "unit": item.get("Data", {}).get("Unit"),
                    "name": name,
                    "id": sensor_id
                }
                
            except (KeyError, IndexError, TypeError):
                continue

        return processed

    async def async_close(self):
        """Ressourcen aufräumen."""
        if self._unsub_timer:
            self._unsub_timer()