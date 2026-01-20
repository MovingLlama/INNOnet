"""Data update coordinator for INNOnet."""
from __future__ import annotations

import logging
from datetime import timedelta, datetime

import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_point_in_time

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
        
        # Variable für den Timer-Handle (zum Abbrechen alter Timer)
        self._unsub_scheduled_update = None

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

                # 3. Fetch Energy Price Components (Base + Fee + Vat)
                # We fetch all three parts to sum them up precisely
                energy_base = await self._fetch_timeseries_moment("energy-base")
                energy_fee = await self._fetch_timeseries_moment("energy-fee")
                energy_vat = await self._fetch_timeseries_moment("energy-vat")
                
                if energy_base: data["energy_base"] = energy_base
                if energy_fee: data["energy_fee"] = energy_fee
                if energy_vat: data["energy_vat"] = energy_vat

                # 4. Fetch Signal Forecast
                signal_forecast = await self._fetch_forecast("tariff-signal", hours=48)
                
                # 5. Calculate Sun Window info
                window_info = self._calculate_sun_window(signal_forecast)
                data.update(window_info)

                if not data:
                    raise UpdateFailed("No data received from INNOnet API.")

                # Wenn wir hier sind, war das Update erfolgreich.
                # Wir planen das nächste exakte Update basierend auf den Sun-Window-Zeiten.
                self._schedule_sun_window_update(data)

                return data

        except (aiohttp.ClientError, Exception) as err:
            # Wenn wir bereits Daten haben, behalten wir diese bei, anstatt abzustürzen.
            # Das löst das Problem mit den "unknown" Werten bei instabiler API.
            if self.data:
                _LOGGER.warning(
                    "Fehler beim Abruf der INNOnet Daten: %s. Verwende zwischengespeicherte Daten.", 
                    err
                )
                return self.data
            
            # Nur wenn wir gar keine Daten haben, werfen wir den Fehler weiter
            raise UpdateFailed(f"Error communicating with API: {err}")

    def _schedule_sun_window_update(self, data: dict):
        """Schedule an update exactly at the next sun window start or end."""
        # Vorherigen Timer löschen, falls vorhanden
        if self._unsub_scheduled_update:
            self._unsub_scheduled_update()
            self._unsub_scheduled_update = None

        now = dt_util.now()
        target_times = []

        # Prüfe Startzeit
        if start_str := data.get("next_sun_start"):
            try:
                start_dt = dt_util.parse_datetime(str(start_str))
                if start_dt and start_dt > now:
                    target_times.append(start_dt)
            except (ValueError, TypeError):
                pass

        # Prüfe Endzeit
        if end_str := data.get("next_sun_end"):
            try:
                end_dt = dt_util.parse_datetime(str(end_str))
                if end_dt and end_dt > now:
                    target_times.append(end_dt)
            except (ValueError, TypeError):
                pass

        if not target_times:
            return

        # Nächsten Zeitpunkt finden
        next_update = min(target_times)
        
        # Sicherheitsabstand von 2 Sekunden, damit die API sicher umgeschaltet hat
        next_update += timedelta(seconds=30)

        _LOGGER.debug("Plane exaktes Update für Sun-Window um: %s", next_update)
        
        self._unsub_scheduled_update = async_track_point_in_time(
            self.hass, self._handle_scheduled_update, next_update
        )

    @callback
    async def _handle_scheduled_update(self, now):
        """Handle the scheduled update."""
        _LOGGER.debug("Führe geplantes Sun-Window Update aus.")
        self._unsub_scheduled_update = None
        await self.async_request_refresh()

    def _extract_data_list(self, json_response: any) -> tuple[list, str | None]:
        """
        Robustly extract data list AND unit from nested JSON.
        Returns: (list_of_items, unit_string)
        """
        unit = None
        items = []

        if isinstance(json_response, list):
            items = json_response
        
        elif isinstance(json_response, dict):
            unit = json_response.get("Unit", json_response.get("unit"))
            
            l1 = json_response.get("Data", json_response.get("data"))
            
            if isinstance(l1, list):
                items = l1
            elif isinstance(l1, dict):
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
                    items, _ = self._extract_data_list(json_data)
                    
                    for item in items:
                        name = item.get("Name", item.get("name", ""))
                        lower_name = name.lower()
                        
                        if "tariff-signal" in lower_name: 
                            self.resolved_names["tariff-signal"] = name
                        
                        if "innonet-tariff" in lower_name: 
                            self.resolved_names["innonet-tariff"] = name
                            
                        # Discover Energy Tariff Components
                        if "public-energy-tariff" in lower_name:
                             if "fee" in lower_name:
                                 self.resolved_names["energy-fee"] = name
                             elif "vat" in lower_name:
                                 self.resolved_names["energy-vat"] = name
                             else:
                                 self.resolved_names["energy-base"] = name
                             
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