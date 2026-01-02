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
            async with async_timeout.timeout(30):
                # 1. Fetch Tariff Signal
                signal_data = await self._fetch_with_fallback("tariff-signal")
                if signal_data:
                    data["tariff_signal"] = signal_data

                # 2. Fetch Innonet Tariff (Price)
                price_data = await self._fetch_with_fallback("innonet-tariff")
                if price_data:
                    data["innonet_tariff"] = price_data

                if not data:
                    # Trigger discovery if we have NO data at all, just in case
                    if not self.resolved_names:
                        await self._discover_timeseries_names()
                    raise UpdateFailed("No data received from INNOnet API.")

                return data

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def _fetch_with_fallback(self, type_prefix: str) -> dict | None:
        """Try to fetch data, resolve names if 404 occurs."""
        # If we haven't resolved names yet, try discovery first to be safe, 
        # especially since we know the ZPN might mismatch the timeseries ID.
        if type_prefix not in self.resolved_names:
             await self._discover_timeseries_names()

        data = await self._fetch_timeseries_moment(type_prefix)
        return data

    async def _discover_timeseries_names(self):
        """Query the API to find the actual names of available timeseries."""
        url = f"{API_BASE_URL}/{self.api_key}/timeseriescollections/selected-data"
        # Using simple params for discovery
        params = {
            "from": "today",
            "to": "today+1d" 
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    json_data = await response.json()
                    
                    # Handle wrappers (Data/data) or list
                    items = []
                    if isinstance(json_data, list):
                        items = json_data
                    elif isinstance(json_data, dict):
                        items = json_data.get("Data", json_data.get("data", []))
                    
                    for item in items:
                        # Handle "Name" (your JSON) vs "name" (docs)
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
        """
        Helper to fetch a single moment value for a timeseries type.
        """
        # Use resolved name if available, otherwise fallback to standard ZPN naming
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        # Loxone Parameters
        # Note: We let aiohttp handle the encoding of params passed as dict.
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
                    # Don't log warning here, let the fallback logic handle it
                    return None
                
                if response.status != 200:
                    return None
                
                json_data = await response.json()
                
                # Handle "Data" vs "data" vs direct list
                data_list = []
                if isinstance(json_data, list):
                    data_list = json_data
                elif isinstance(json_data, dict):
                    data_list = json_data.get("Data", json_data.get("data", []))

                if isinstance(data_list, list) and len(data_list) > 0:
                    return data_list[0]
                
                return None
        except Exception as e:
            _LOGGER.error(f"Exception fetching {ts_name}: {e}")
            return None