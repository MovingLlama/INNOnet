"""Config flow for INNOnet integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, API_BASE_URL, CONF_ZPN

_LOGGER = logging.getLogger(__name__)

# Schema now includes optional ZPN for fallback
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_ZPN): str,
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for INNOnet."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Strip whitespace to prevent copy-paste errors
            api_key = user_input[CONF_API_KEY].strip()
            manual_zpn = user_input.get(CONF_ZPN)
            
            zpn = None

            if manual_zpn:
                zpn = manual_zpn.strip()
            else:
                zpn = await self._validate_and_discover_zpn(api_key)

            if zpn:
                await self.async_set_unique_id(zpn)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"INNOnet ({zpn})",
                    data={
                        CONF_API_KEY: api_key,
                        CONF_ZPN: zpn,
                    },
                )
            else:
                errors["base"] = "discovery_failed"

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "zpn_help": "Falls die automatische Erkennung fehlschlägt, gib hier deine ZPN ein."
            }
        )

    async def _validate_and_discover_zpn(self, api_key: str) -> str | None:
        """
        Validate API key and discover ZPN.
        """
        session = async_get_clientsession(self.hass)
        url = f"{API_BASE_URL}/{api_key}/timeseriescollections/selected-data"
        
        params = {
            "from": "today",
            "to": "today+1d", 
            "datatype": "tariff-signal"
        }

        try:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    _LOGGER.error("INNOnet API returned status %s during setup", response.status)
                    return None
                
                data = await response.json()
                
                items = data
                if isinstance(data, dict) and "data" in data: # Case 'data' (lowercase)
                    items = data["data"]
                elif isinstance(data, dict) and "Data" in data: # Case 'Data' (uppercase)
                    items = data["Data"]
                
                if isinstance(items, list) and len(items) > 0:
                    for item in items:
                        # Handle both "Name" and "name"
                        ts_name = item.get("Name", item.get("name", ""))
                        
                        if ts_name.lower().startswith("tariff-signal-"):
                            zpn = ts_name[14:] # len("tariff-signal-") is 14
                            _LOGGER.debug("Discovered ZPN: %s", zpn)
                            return zpn
                
                _LOGGER.error("Could not find a valid 'tariff-signal-{ZPN}' in API response.")
                return None

        except aiohttp.ClientError as err:
            return None
        except Exception as err:
            return None