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
                    # If both failed, raise an error
                    raise UpdateFailed("No data received from INNOnet API (Check ZPN or API Key)")

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
        
        # Construct parameters for "Momentanwert" (Instantaneous value)
        # IMPORTANT: The '+' symbol in 'now[30m+30m' must be encoded as '%2B'.
        # Standard requests often treat '+' as space. We construct the query string manually 
        # to ensure strict compliance with HAKOM TSM API requirements mentioned in docs.
        
        # from=now[30m
        # to=now[30m+30m  --> Encoded: now[30m%2B30m
        # aggregation=AtTheMoment
        
        params_str = "from=now[30m&to=now[30m%2B30m&aggregation=AtTheMoment"
        
        # We append the params manually to the URL to avoid aggressive encoding/decoding issues
        full_url = f"{url}?{params_str}"
        
        try:
            async with self.session.get(full_url) as response:
                if response.status == 404:
                    _LOGGER.warning(f"Failed to fetch {ts_name}: 404 Not Found. Please check if ZPN '{self.zpn}' is correct and active.")
                    return None
                
                if response.status != 200:
                    _LOGGER.warning(f"Failed to fetch {ts_name}: Status {response.status}")
                    return None
                
                json_data = await response.json()
                
                if "data" in json_data and len(json_data["data"]) > 0:
                    # Return the first data point found
                    return json_data["data"][0]
                
                return None
        except Exception as e:
            _LOGGER.error(f"Exception fetching {ts_name}: {e}")
            return None