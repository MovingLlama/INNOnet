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
        
        # Cache for resolved timeseries names (e.g. if ZPN guess is wrong)
        self.resolved_names: dict[str, str] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # Documentation explicitly requests update interval > 5 minutes.
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
                    raise UpdateFailed("No data received from INNOnet API. Check API Key or ZPN.")

                return data

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def _fetch_with_fallback(self, type_prefix: str) -> dict | None:
        """Try to fetch data, resolve names if 404 occurs."""
        # First attempt
        data = await self._fetch_timeseries_moment(type_prefix)
        
        # If successful, return
        if data is not None:
            return data
            
        # If failed (likely 404 or name mismatch), try to auto-discover names once
        if not self.resolved_names:
            _LOGGER.info(f"Data not found for {type_prefix}. Attempting to auto-discover timeseries names...")
            await self._discover_timeseries_names()
            
            # Retry with new names
            data = await self._fetch_timeseries_moment(type_prefix)
            
        return data

    async def _discover_timeseries_names(self):
        """Query the API to find the actual names of available timeseries."""
        url = f"{API_BASE_URL}/{self.api_key}/timeseriescollections/selected-data"
        params = {
            "from": "today",
            "to": "today+1d",
            "datatype": "tariff-signal"
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    json_data = await response.json()
                    
                    # Handle both list and dict wrapper
                    items = json_data.get("data", []) if isinstance(json_data, dict) else json_data
                    
                    if isinstance(items, list):
                        for item in items:
                            name = item.get("name", "")
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
        
        # Loxone Parameters:
        # from = now[15m
        # to = now[15m+15m
        # interval = Minute
        # intervalMultiplier = 15
        # aggregation = AtTheMoment
        
        # We use a dictionary for params to let aiohttp handle safe encoding.
        # This prevents double-encoding issues with the manual string construction.
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
                    _LOGGER.warning(f"Timeseries '{ts_name}' not found (404).")
                    return None
                
                if response.status != 200:
                    _LOGGER.debug(f"Failed to fetch {ts_name}: Status {response.status}")
                    return None
                
                json_data = await response.json()
                
                # Check for list wrapper or direct data object
                data_list = json_data.get("data", []) if isinstance(json_data, dict) else json_data
                
                if isinstance(data_list, list) and len(data_list) > 0:
                    return data_list[0]
                
                return None
        except Exception as e:
            _LOGGER.error(f"Exception fetching {ts_name}: {e}")
            return None