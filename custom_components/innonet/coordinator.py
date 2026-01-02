"""Data update coordinator for INNOnet."""
from __future__ import annotations

import logging
from datetime import timedelta

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
                # 1. Discover Names if missing (Autocorrect ZPN mismatch)
                if not self.resolved_names:
                    await self._discover_timeseries_names()

                # 2. Fetch Current Price
                price_data = await self._fetch_timeseries_moment("innonet-tariff")
                if price_data:
                    data["current_price"] = price_data
                else:
                    _LOGGER.debug("No current price data found.")

                # 3. Fetch Signal Forecast (Next 48h for calculation)
                # Fetching 48h ensures we find the next window even if it's tomorrow after 16:00
                signal_forecast = await self._fetch_forecast("tariff-signal", hours=48)
                
                # 4. Calculate Sun Window info
                window_info = self._calculate_sun_window(signal_forecast)
                data.update(window_info)

                if not data:
                    raise UpdateFailed("No data received from INNOnet API.")

                return data

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def _extract_data_list(self, json_response: any) -> list:
        """
        Robustly extract the list of data points from nested JSON.
        Structure can be:
        - [ ... ]
        - { "Data": [ ... ] }
        - { "Data": { "Data": [ ... ] } }  <-- This was likely the issue
        """
        if isinstance(json_response, list):
            return json_response
        
        if isinstance(json_response, dict):
            # Level 1 check
            l1 = json_response.get("Data", json_response.get("data"))
            
            if isinstance(l1, list):
                return l1
            
            if isinstance(l1, dict):
                # Level 2 check (Nested Data object)
                l2 = l1.get("Data", l1.get("data"))
                if isinstance(l2, list):
                    return l2
                    
        return []

    def _calculate_sun_window(self, forecast_list: list[dict] | None) -> dict:
        """Analyze forecast to find Sun Window (-1)."""
        result = {
            "sun_window_active": False,
            "next_sun_start": None,
            "next_sun_end": None,
            "tariff_signal_now": None
        }

        if not forecast_list:
            return result

        # 1. Current State (First item is 'now')
        current_item = forecast_list[0]
        current_val = current_item.get("v")
        result["tariff_signal_now"] = current_item
        
        # Check if active (-1 is Sun Window)
        is_active = (current_val == -1)
        result["sun_window_active"] = is_active

        # 2. Find Start/End
        found_start = False
        
        if is_active:
            # Currently Active: Start is Now (or previous, but for UI 'now' is fine)
            result["next_sun_start"] = current_item.get("t")
            found_start = True
            
            # Find End: First value that is NOT -1
            for item in forecast_list:
                if item.get("v") != -1:
                    result["next_sun_end"] = item.get("t")
                    break
        else:
            # Currently Inactive: Find next Start (-1)
            for i, item in enumerate(forecast_list):
                if item.get("v") == -1:
                    result["next_sun_start"] = item.get("t")
                    found_start = True
                    
                    # From here, find the End
                    for sub_item in forecast_list[i:]:
                        if sub_item.get("v") != -1:
                            result["next_sun_end"] = sub_item.get("t")
                            break
                    break
            
        return result

    def _normalize_data(self, item: dict) -> dict:
        """Normalize API keys."""
        if not item: return item
        # API often uses PascalCase, sensor expects 'v', 'f', 't'
        if "Value" in item: item["v"] = item["Value"]
        if "Flag" in item: item["f"] = item["Flag"]
        if "From" in item: item["t"] = item["From"]
        return item

    async def _discover_timeseries_names(self):
        """Query 'selected-data' to find correct timeseries names (fix ZPN mismatch)."""
        url = f"{API_BASE_URL}/{self.api_key}/timeseriescollections/selected-data"
        params = {"from": "today", "to": "today+1d"}
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    json_data = await response.json()
                    # Use robust extraction here too
                    items = self._extract_data_list(json_data)
                    
                    for item in items:
                        name = item.get("Name", item.get("name", ""))
                        if "tariff-signal" in name: 
                            self.resolved_names["tariff-signal"] = name
                            _LOGGER.debug(f"Resolved tariff-signal: {name}")
                        if "innonet-tariff" in name: 
                            self.resolved_names["innonet-tariff"] = name
                            _LOGGER.debug(f"Resolved innonet-tariff: {name}")
        except Exception as e:
            _LOGGER.warning(f"Discovery failed: {e}")

    async def _fetch_timeseries_moment(self, type_prefix: str) -> dict | None:
        """Fetch current single value."""
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        # Params matching Loxone logic (15min grid)
        params = {
            "from": "now[15m", "to": "now[15m+15m",
            "interval": "Minute", "intervalMultiplier": "15", "aggregation": "AtTheMoment"
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    json_data = await response.json()
                    items = self._extract_data_list(json_data)
                    if items: 
                        return self._normalize_data(items[0])
        except Exception:
            pass
        return None

    async def _fetch_forecast(self, type_prefix: str, hours: int) -> list[dict]:
        """Fetch forecast data."""
        if type_prefix not in self.resolved_names:
            await self._discover_timeseries_names()
            
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        params = {
            "from": "now[15m",
            "to": f"now[15m+{hours}h",
            "interval": "Minute",
            "intervalMultiplier": "15",
            "aggregation": "AtTheMoment"
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    json_data = await response.json()
                    items = self._extract_data_list(json_data)
                    if items: 
                        return [self._normalize_data(i) for i in items]
        except Exception:
            pass
        return []