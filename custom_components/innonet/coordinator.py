"""Data update coordinator for INNOnet."""
from __future__ import annotations

import logging
from datetime import timedelta, datetime

import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, API_BASE_URL, CONF_ZPN, UPDATE_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


class InnonetDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching INNOnet data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.api_key = entry.data[CONF_API_KEY]
        self.zpn = entry.data[CONF_ZPN]
        self.session = async_get_clientsession(hass)
        self.resolved_names: dict[str, str] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from API."""
        data = {}

        try:
            async with async_timeout.timeout(45):
                # 1. Check/Discover Names first if needed
                if not self.resolved_names:
                    await self._discover_timeseries_names()

                # 2. Fetch Current Price (for History Graph)
                price_data = await self._fetch_timeseries_moment("innonet-tariff")
                if price_data:
                    data["current_price"] = price_data

                # 3. Fetch Signal Forecast (Next 48h to find next Sun Window)
                # We need a longer range to find the next window if it's currently night
                signal_forecast = await self._fetch_forecast("tariff-signal", hours=48)
                
                # 4. Calculate Sun Window Logic
                window_info = self._calculate_sun_window(signal_forecast)
                data.update(window_info)

                if not data:
                    raise UpdateFailed("No data received from INNOnet API.")

                return data

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def _calculate_sun_window(self, forecast_list: list[dict] | None) -> dict:
        """
        Analyze forecast to find current status and next start/end of sun window (Value = -1).
        """
        result = {
            "sun_window_active": False,
            "next_sun_start": None,
            "next_sun_end": None,
            "tariff_signal_now": None # Raw value for the enum sensor
        }

        if not forecast_list:
            return result

        # Sort by time just in case
        # Assuming ISO format dates strings sort correctly, but safe to trust order usually
        
        # 1. Determine Current State (First item in forecast is usually 'now' or close to it)
        current_item = forecast_list[0]
        current_val = current_item.get("v")
        result["tariff_signal_now"] = current_item
        
        is_active = (current_val == -1)
        result["sun_window_active"] = is_active

        # 2. Find Start and End
        found_start = False
        found_end = False

        if is_active:
            # We are IN the window.
            # Start is effectively "now" (or the timestamp of current item)
            result["next_sun_start"] = current_item.get("t")
            
            # Find End: Look for first item that is NOT -1
            for item in forecast_list:
                if item.get("v") != -1:
                    result["next_sun_end"] = item.get("t")
                    found_end = True
                    break
        else:
            # We are NOT in the window.
            # Find Start: Look for first item that IS -1
            for item in forecast_list:
                if item.get("v") == -1:
                    result["next_sun_start"] = item.get("t")
                    found_start = True
                    # Once start is found, continue from there to find End
                    # We can iterate the rest of the list
                    start_index = forecast_list.index(item)
                    for sub_item in forecast_list[start_index:]:
                        if sub_item.get("v") != -1:
                            result["next_sun_end"] = sub_item.get("t")
                            found_end = True
                            break
                    break
            
        return result

    def _normalize_data(self, item: dict) -> dict:
        """Normalize API keys (Value -> v, etc)."""
        if not item: return item
        if "Value" in item: item["v"] = item["Value"]
        if "Flag" in item: item["f"] = item["Flag"]
        if "From" in item: item["t"] = item["From"]
        return item

    async def _discover_timeseries_names(self):
        """Query API for correct timeseries names."""
        url = f"{API_BASE_URL}/{self.api_key}/timeseriescollections/selected-data"
        params = {"from": "today", "to": "today+1d"}
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    json_data = await response.json()
                    items = json_data if isinstance(json_data, list) else json_data.get("Data", json_data.get("data", []))
                    for item in items:
                        name = item.get("Name", item.get("name", ""))
                        if "tariff-signal" in name: self.resolved_names["tariff-signal"] = name
                        if "innonet-tariff" in name: self.resolved_names["innonet-tariff"] = name
        except Exception:
            pass

    async def _fetch_timeseries_moment(self, type_prefix: str) -> dict | None:
        """Fetch current single value."""
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        params = {
            "from": "now[15m", "to": "now[15m+15m",
            "interval": "Minute", "intervalMultiplier": "15", "aggregation": "AtTheMoment"
        }
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data if isinstance(data, list) else data.get("Data", data.get("data", []))
                    if items: return self._normalize_data(items[0])
        except Exception:
            pass
        return None

    async def _fetch_forecast(self, type_prefix: str, hours: int) -> list[dict]:
        """Fetch forecast data."""
        # Ensure we have a name
        if type_prefix not in self.resolved_names:
            await self._discover_timeseries_names()
            
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        # Fetch 15-minute intervals for better precision on start/end times
        # from=now[15m to=now[15m+48h
        params = {
            "from": "now[15m",
            "to": f"now[15m+{hours}h",
            "interval": "Minute",
            "intervalMultiplier": "15", # Keep 15m resolution
            "aggregation": "AtTheMoment" # Or Average, but for Signal "AtTheMoment" is safer
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data if isinstance(data, list) else data.get("Data", data.get("data", []))
                    if items: return [self._normalize_data(i) for i in items]
        except Exception:
            pass
        return []