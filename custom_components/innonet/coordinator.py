"""DataUpdateCoordinator für die INNOnet Integration."""
from datetime import timedelta
import logging
import async_timeout
import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_change
from homeassistant.const import CONF_API_KEY

from .const import DOMAIN, BASE_URL

_LOGGER = logging.getLogger(__name__)

class InnoNetDataUpdateCoordinator(DataUpdateCoordinator):
    """Klasse zur Verwaltung des Datenabrufs von der INNOnet API."""

    def __init__(self, hass: HomeAssistant, entry):
        """Initialisierung des Coordinators."""
        self.api_key = entry.data.get(CONF_API_KEY)
        self.entry = entry
        
        # Speicher für persistente Werte (wenn der neue Wert 0 ist)
        self._persistent_values = {}

        # Wir setzen update_interval auf None, da wir die Aktualisierung 
        # manuell über async_track_time_change steuern (10 Sek. nach Punkt).
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )

        # Registriere den Timer: Jede Stunde (:00), bei Sekunde 10
        self._unsub_timer = async_track_time_change(
            hass,
            self._async_scheduled_update,
            minute=0,
            second=10
        )

    @callback
    async def _async_scheduled_update(self, _now=None):
        """Wird vom Timer aufgerufen, um die Daten zu aktualisieren."""
        _LOGGER.debug("Starte geplante Aktualisierung (10s nach der vollen Stunde)")
        await self.async_refresh()

    async def _async_update_data(self):
        """Daten von der API abrufen."""
        # Dynamische URL mit dem API-Key aus der Konfiguration
        url = f"https://app-innonnetwebtsm-dev.azurewebsites.net/api/extensions/timeseriesauthorization/repositories/INNOnet-prod/apikey/{self.api_key}/timeseriescollections/selected-data?from=now[30m&to=now[30m%2B1h&interval=hour"

        try:
            async with async_timeout.timeout(30):
                async with aiohttp.ClientSession() as session:
                    response = await session.get(url)
                    response.raise_for_status()
                    data = await response.json()
                    
                    return self._process_data(data)

        except Exception as err:
            raise UpdateFailed(f"Fehler beim Abruf der Daten: {err}")

    def _process_data(self, raw_data):
        """Verarbeitet die Rohdaten und implementiert die Nullwert-Logik."""
        processed = {}

        for item in raw_data:
            name = item.get("Name")
            sensor_id = item.get("ID")
            
            # Schlüssel für die Speicherung (Kombination aus Name und ID)
            storage_key = f"{name}_{sensor_id}"
            
            try:
                # Extrahiere den Wert aus der Zeitreihe (Data[0])
                data_points = item.get("Data", {}).get("Data", [])
                
                if not data_points:
                    _LOGGER.warning("Keine Datenpunkte für %s empfangen", name)
                    continue
                
                new_value = data_points[0].get("Value")
                
                # Logik: Wenn der neue Wert 0 ist, nimm den alten Wert
                if new_value == 0 or new_value == 0.0:
                    prev_value = self._persistent_values.get(storage_key)
                    if prev_value is not None:
                        _LOGGER.debug("Wert für %s ist 0. Verwende vorherigen Wert: %s", name, prev_value)
                        final_value = prev_value
                    else:
                        final_value = 0
                else:
                    # Gültigen Wert speichern und verwenden
                    self._persistent_values[storage_key] = new_value
                    final_value = new_value
                
                processed[storage_key] = {
                    "value": final_value,
                    "unit": item.get("Data", {}).get("Unit"),
                    "name": name,
                    "id": sensor_id
                }
                
            except (IndexError, KeyError, TypeError) as err:
                _LOGGER.error("Fehler beim Parsen von %s: %s", name, err)

        return processed

    async def async_close(self):
        """Ressourcen aufräumen."""
        if self._unsub_timer:
            self._unsub_timer()