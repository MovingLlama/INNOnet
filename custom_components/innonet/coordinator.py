"""Data update coordinator for INNOnet."""
from __future__ import annotations

import logging
from datetime import timedelta
import urllib.parse

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
        
        # Cache for resolved timeseries names
        self.resolved_names: dict[str, str] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> dict:
        """
        Fetch data from API.
        """
        data = {}

        try:
            async with async_timeout.timeout(45): # Increased timeout for multiple calls
                # 1. Fetch Tariff Signal
                signal_data = await self._fetch_with_fallback("tariff-signal")
                if signal_data:
                    data["tariff_signal"] = signal_data

                # 2. Fetch Innonet Tariff (Current Price)
                price_data = await self._fetch_with_fallback("innonet-tariff")
                if price_data:
                    data["innonet_tariff"] = price_data

                # 3. Fetch Forecast (Next 24h)
                # We only fetch forecast if we successfully found the tariff timeseries name
                if "innonet-tariff" in self.resolved_names or price_data:
                    forecast_data = await self._fetch_forecast("innonet-tariff")
                    if forecast_data:
                        data["price_forecast"] = forecast_data

                if not data:
                    # Trigger discovery if we have NO data at all
                    if not self.resolved_names:
                        await self._discover_timeseries_names()
                    raise UpdateFailed("No data received from INNOnet API.")

                return data

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def _normalize_data(self, item: dict) -> dict:
        """
        Normalize API response keys to standard lowercase 'v', 'f', 't'.
        API sometimes returns 'Value', 'Flag', 'From'.
        """
        if not item:
            return item
        
        # Map 'Value' to 'v'
        if "Value" in item and "v" not in item:
            item["v"] = item["Value"]
        
        # Map 'Flag' to 'f'
        if "Flag" in item and "f" not in item:
            item["f"] = item["Flag"]
            
        # Map 'From' to 't' (timestamp)
        if "From" in item and "t" not in item:
            item["t"] = item["From"]
            
        return item

    async def _fetch_with_fallback(self, type_prefix: str) -> dict | None:
        """Try to fetch data, resolve names if 404 occurs."""
        if type_prefix not in self.resolved_names:
             await self._discover_timeseries_names()

        data = await self._fetch_timeseries_moment(type_prefix)
        return data

    async def _discover_timeseries_names(self):
        """Query the API to find the actual names of available timeseries."""
        url = f"{API_BASE_URL}/{self.api_key}/timeseriescollections/selected-data"
        params = {
            "from": "today",
            "to": "today+1d" 
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    json_data = await response.json()
                    
                    items = []
                    if isinstance(json_data, list):
                        items = json_data
                    elif isinstance(json_data, dict):
                        items = json_data.get("Data", json_data.get("data", []))
                    
                    for item in items:
                        name = item.get("Name", item.get("name", ""))
                        
                        if "tariff-signal" in name:
                            self.resolved_names["tariff-signal"] = name
                            _LOGGER.info(f"Discovered tariff-signal name: {name}")
                        if "innonet-tariff" in name:
                            self.resolved_names["innonet-tariff"] = name
                            _LOGGER.info(f"Discovered innonet-tariff name: {name}")
                                
        except Exception as err:
            _LOGGER.warning(f"Auto-discovery failed: {err}")

    async def _fetch_timeseries_moment(self, type_prefix: str) -> dict | None:
        """Fetch a single moment value."""
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        params = {
            "from": "now[15m",
            "to": "now[15m+15m",
            "interval": "Minute",
            "intervalMultiplier": "15",
            "aggregation": "AtTheMoment"
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 404:
                    return None
                if response.status != 200:
                    return None
                
                json_data = await response.json()
                
                data_list = []
                if isinstance(json_data, list):
                    data_list = json_data
                elif isinstance(json_data, dict):
                    data_list = json_data.get("Data", json_data.get("data", []))

                if isinstance(data_list, list) and len(data_list) > 0:
                    return self._normalize_data(data_list[0])
                
                return None
        except Exception as e:
            _LOGGER.error(f"Exception fetching {ts_name}: {e}")
            return None

    async def _fetch_forecast(self, type_prefix: str) -> list[dict] | None:
        """Fetch forecast data (next 24h, hourly aggregated)."""
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        # Params for 24h forecast, hourly aggregation
        params = {
            "from": "now[1h", # Start of current hour
            "to": "now[1h+24h", # +24 hours
            "interval": "Hour",
            "intervalMultiplier": "1",
            "aggregation": "Average" # Average price per hour
        }
        
        # We manually construct query partly if needed, but dict is safer for simple chars.
        # Note: + char needs care, but aiohttp usually handles it if passed in dict correctly.
        # However, to be absolutely safe matching the Loxone logic for encoding:
        params_str = "from=now[1h&to=now[1h%2B24h&interval=Hour&intervalMultiplier=1&aggregation=Average"
        full_url = f"{url}?{params_str}"

        try:
            async with self.session.get(full_url) as response:
                if response.status != 200:
                    return None
                
                json_data = await response.json()
                
                data_list = []
                if isinstance(json_data, list):
                    data_list = json_data
                elif isinstance(json_data, dict):
                    data_list = json_data.get("Data", json_data.get("data", []))

                if isinstance(data_list, list):
                    # Normalize all items
                    return [self._normalize_data(item) for item in data_list]
                
                return None
        except Exception as e:
            _LOGGER.warning(f"Exception fetching forecast for {ts_name}: {e}")
            return None