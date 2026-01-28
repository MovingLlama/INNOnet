"""DataUpdateCoordinator für die INNOnet Integration."""
import logging
import async_timeout
import aiohttp
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_change
from homeassistant.const import CONF_API_KEY

from .const import DOMAIN, BASE_URL, UPDATE_OFFSET_SECONDS, UPDATE_CRON_MINUTE

_LOGGER = logging.getLogger(__name__)

class InnonetDataUpdateCoordinator(DataUpdateCoordinator):
    """Verwaltet den Datenabruf und die Persistenz."""

    def __init__(self, hass: HomeAssistant, entry):
        self.api_key = entry.data.get(CONF_API_KEY)
        self.entry = entry
        self._persistent_values = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )

        # Stündlicher Timer (10 Sek. nach voll)
        self._unsub_timer = async_track_time_change(
            hass,
            self._async_scheduled_update,
            minute=UPDATE_CRON_MINUTE,
            second=UPDATE_OFFSET_SECONDS
        )

    @callback
    async def _async_scheduled_update(self, _now=None):
        _LOGGER.debug("Geplantes Update um 10s nach der vollen Stunde")
        await self.async_refresh()

    async def _async_update_data(self):
        # Wir rufen 24 Stunden ab, um die nächsten Sonnenfenster zuverlässig zu finden
        url = f"{BASE_URL}/{self.api_key}/timeseriescollections/selected-data?from=now[30m&to=now[30m%2B24h&interval=hour"
        
        try:
            async with async_timeout.timeout(20):
                async with aiohttp.ClientSession() as session:
                    response = await session.get(url)
                    response.raise_for_status()
                    data = await response.json()
                    return self._process_data(data)
        except Exception as err:
            _LOGGER.error("API Fehler: %s", err)
            raise UpdateFailed(f"Fehler beim Abruf: {err}")

    def _process_data(self, raw_data):
        processed = {}
        if not raw_data:
            return processed

        for item in raw_data:
            name = item.get("Name")
            sensor_id = item.get("ID")
            storage_key = f"{name}_{sensor_id}"
            
            data_points = item.get("Data", {}).get("Data", [])
            if not data_points:
                val = self._persistent_values.get(storage_key, 0.0)
            else:
                # Aktueller Wert
                new_value = data_points[0].get("Value")
                
                # Nullwert-Schutz
                if new_value == 0 or new_value == 0.0:
                    val = self._persistent_values.get(storage_key, 0.0)
                else:
                    self._persistent_values[storage_key] = new_value
                    val = new_value
            
            processed[storage_key] = {
                "value": val,
                "unit": item.get("Data", {}).get("Unit"),
                "name": name,
                "id": sensor_id,
                "time_series": data_points
            }

        return processed

    async def async_close(self):
        if self._unsub_timer:
            self._unsub_timer()