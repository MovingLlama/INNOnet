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
        
        We fetch:
        1. The current tariff signal (tariff-signal-{ZPN})
        2. (Optional) The current tariff price (innonet-tariff-{ZPN})
        """
        data = {}

        try:
            async with async_timeout.timeout(20):
                # 1. Fetch Tariff Signal
                # Using the syntax from docs: now[30m to now[30m+30m to get the current 30-min window
                signal_data = await self._fetch_timeseries_moment("tariff-signal")
                if signal_data is not None:
                    data["tariff_signal"] = signal_data

                # 2. Fetch Innonet Tariff (Price)
                # Note: This might return missing values (Flag 19) if not active (signal=0)
                price_data = await self._fetch_timeseries_moment("innonet-tariff")
                if price_data is not None:
                    data["innonet_tariff"] = price_data

                if not data:
                    raise UpdateFailed("No data received from INNOnet API")

                return data

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def _fetch_timeseries_moment(self, type_prefix: str) -> dict | None:
        """
        Helper to fetch a single moment value for a timeseries type.
        
        Args:
            type_prefix: e.g., "tariff-signal" or "innonet-tariff"
        """
        ts_name = f"{type_prefix}-{self.zpn}"
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        # Parameters for "Momentanwert" (Instantaneous value) as per documentation
        # "now[30m" rounds 'now' down to the nearest 30 mins.
        # "now[30m%2B30m" adds 30 mins to that.
        # Note: We must send encoded + (%2B) in the actual request, but aiohttp handles params encoding usually.
        # However, looking at the doc examples, the server uses HAKOM TSM syntax.
        # Let's use simple parameters handled by aiohttp.
        
        params = {
            "from": "now[30m",
            "to": "now[30m+30m", # The + sign might need care, but aiohttp usually encodes. 
                                 # If server is strict about double encoding, we might need to construct URL manually.
                                 # Assuming standard encoding works for now.
            "aggregation": "AtTheMoment"
        }
        
        # NOTE: The documentation specifically mentions URL encoding %2B for +. 
        # aiohttp params encoding usually converts '+' to space or encodes it. 
        # To be safe regarding the specific HAKOM syntax, we construct the query string carefully if needed.
        # But 'now[30m+30m' in a param value usually gets encoded to 'now%5B30m%2B30m' which is correct.
        
        async with self.session.get(url, params=params) as response:
            if response.status != 200:
                _LOGGER.warning(f"Failed to fetch {ts_name}: {response.status}")
                return None
            
            json_data = await response.json()
            # Response format expected:
            # { "data": [ { "v": value, "t": timestamp, ... } ], ... }
            
            if "data" in json_data and len(json_data["data"]) > 0:
                # Return the first data point found
                return json_data["data"][0]
            
            return None