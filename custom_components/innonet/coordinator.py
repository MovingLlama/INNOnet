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
                # 1. Discover Names
                if not self.resolved_names:
                    await self._discover_timeseries_names()

                # 2. Fetch Grid Price (innonet-tariff)
                grid_data = await self._fetch_timeseries_moment("innonet-tariff")
                if grid_data:
                    data["grid_price"] = grid_data

                # 3. Fetch Energy Price (public-energy-tariff)
                energy_data = await self._fetch_timeseries_moment("energy-tariff")
                if energy_data:
                    data["energy_price"] = energy_data

                # 4. Fetch Signal Forecast
                signal_forecast = await self._fetch_forecast("tariff-signal", hours=48)
                
                # 5. Calculate Sun Window info
                window_info = self._calculate_sun_window(signal_forecast)
                data.update(window_info)

                if not data:
                    raise UpdateFailed("No data received from INNOnet API.")

                return data

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def _extract_data_list(self, json_response: any) -> tuple[list, str | None]:
        """
        Robustly extract data list AND unit from nested JSON.
        Returns: (list_of_items, unit_string)
        """
        unit = None
        items = []

        if isinstance(json_response, list):
            # Flat list, no unit info usually available at top level in this case
            items = json_response
        
        elif isinstance(json_response, dict):
            # Try to find Unit at top level
            unit = json_response.get("Unit", json_response.get("unit"))
            
            # Level 1
            l1 = json_response.get("Data", json_response.get("data"))
            
            if isinstance(l1, list):
                items = l1
            elif isinstance(l1, dict):
                # Level 2 (Nested Data object)
                # Unit might be inside the first Data object
                if not unit:
                    unit = l1.get("Unit", l1.get("unit"))
                
                l2 = l1.get("Data", l1.get("data"))
                if isinstance(l2, list):
                    items = l2

        return items, unit

    def _calculate_sun_window(self, forecast_list: list[dict] | None) -> dict:
        """Analyze forecast to find Sun Window (Value = 1)."""
        result = {
            "sun_window_active": False,
            "next_sun_start": None,
            "next_sun_end": None,
            "tariff_signal_now": None
        }

        if not forecast_list:
            return result
        
        SUN_WINDOW_VALUE = 1

        current_item = forecast_list[0]
        current_val = current_item.get("v")
        result["tariff_signal_now"] = current_item
        
        is_active = (current_val == SUN_WINDOW_VALUE)
        result["sun_window_active"] = is_active

        if is_active:
            result["next_sun_start"] = current_item.get("t")
            for item in forecast_list:
                if item.get("v") != SUN_WINDOW_VALUE:
                    result["next_sun_end"] = item.get("t")
                    break
        else:
            for i, item in enumerate(forecast_list):
                if item.get("v") == SUN_WINDOW_VALUE:
                    result["next_sun_start"] = item.get("t")
                    for sub_item in forecast_list[i:]:
                        if sub_item.get("v") != SUN_WINDOW_VALUE:
                            result["next_sun_end"] = sub_item.get("t")
                            break
                    break
            
        return result

    def _normalize_data(self, item: dict, unit: str | None = None) -> dict:
        """Normalize keys and convert unit if necessary."""
        if not item: return item
        
        if "Value" in item: item["v"] = item["Value"]
        if "Flag" in item: item["f"] = item["Flag"]
        if "From" in item: item["t"] = item["From"]
        
        # Convert Cent/kWh to EUR/kWh
        # We assume if no unit is given, it's already correct or unknown.
        # But specifically check for "Cent" (case insensitive)
        if unit and "cent" in unit.lower() and item.get("v") is not None:
             try:
                 item["v"] = float(item["v"]) / 100.0
             except (ValueError, TypeError):
                 pass

        return item

    async def _discover_timeseries_names(self):
        """Find correct timeseries names."""
        url = f"{API_BASE_URL}/{self.api_key}/timeseriescollections/selected-data"
        params = {"from": "today", "to": "today+1d"}
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    json_data = await response.json()
                    # Just need items here, unit doesn't matter for discovery
                    items, _ = self._extract_data_list(json_data)
                    
                    for item in items:
                        name = item.get("Name", item.get("name", ""))
                        lower_name = name.lower()
                        
                        if "tariff-signal" in lower_name: 
                            self.resolved_names["tariff-signal"] = name
                        
                        if "innonet-tariff" in lower_name: 
                            self.resolved_names["innonet-tariff"] = name
                            
                        # Find Public Energy Tariff (excluding Fee and Vat)
                        if "public-energy-tariff" in lower_name and "fee" not in lower_name and "vat" not in lower_name:
                             self.resolved_names["energy-tariff"] = name
                             
        except Exception:
            pass

    async def _fetch_timeseries_moment(self, type_prefix: str) -> dict | None:
        """Fetch current single value with unit conversion."""
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        params_str = "from=now[15m&to=now[15m%2B15m&interval=Minute&intervalMultiplier=15&aggregation=AtTheMoment"
        full_url = f"{url}?{params_str}"
        
        try:
            async with self.session.get(full_url) as response:
                if response.status == 200:
                    json_data = await response.json()
                    items, unit = self._extract_data_list(json_data)
                    if items: 
                        return self._normalize_data(items[0], unit)
        except Exception:
            pass
        return None

    async def _fetch_forecast(self, type_prefix: str, hours: int) -> list[dict]:
        """Fetch forecast data."""
        if type_prefix not in self.resolved_names:
            await self._discover_timeseries_names()
            
        ts_name = self.resolved_names.get(type_prefix, f"{type_prefix}-{self.zpn}")
        url = f"{API_BASE_URL}/{self.api_key}/timeseries/{ts_name}/data"
        
        params_str = f"from=now[15m&to=now[15m%2B{hours}h&interval=Minute&intervalMultiplier=15&aggregation=AtTheMoment"
        full_url = f"{url}?{params_str}"
        
        try:
            async with self.session.get(full_url) as response:
                if response.status == 200:
                    json_data = await response.json()
                    items, unit = self._extract_data_list(json_data)
                    if items: 
                        return [self._normalize_data(i, unit) for i in items]
        except Exception:
            pass
        return []