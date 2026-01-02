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
                # Use manually provided ZPN and strip whitespace
                zpn = manual_zpn.strip()
                # Optional: Verify validity by making a quick API call here if desired
                # For now, we trust the user input to allow setup even if API is glitchy
            else:
                # Try auto-discovery
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
                # Discovery failed and no manual ZPN provided
                errors["base"] = "discovery_failed"

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "zpn_help": "Wenn die automatische Erkennung fehlschlägt, gib hier deine Zählpunktnummer (ZPN) ein."
            }
        )

    async def _validate_and_discover_zpn(self, api_key: str) -> str | None:
        """
        Validate API key and discover ZPN.
        """
        session = async_get_clientsession(self.hass)
        url = f"{API_BASE_URL}/{api_key}/timeseriescollections/selected-data"
        
        # Changed to today+1d to ensure we get a non-empty range which might help 
        # API return the metadata correctly.
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
                
                # Debug logging to help troubleshoot if it fails again
                _LOGGER.debug("INNOnet Discovery Response: %s", data)

                # Handle potential "data" wrapper in response
                items = data
                if isinstance(data, dict) and "data" in data:
                    items = data["data"]
                
                if isinstance(items, list) and len(items) > 0:
                    for item in items:
                        ts_name = item.get("name", "")
                        # Case insensitive check
                        if ts_name.lower().startswith("tariff-signal-"):
                            # Extract ZPN: "tariff-signal-123456" -> "123456"
                            # Split by first occurrence of "-" might be safer if ZPN has dashes?
                            # Usually format is fixed, but let's be careful.
                            # Assuming standard format "tariff-signal-{ZPN}"
                            zpn = ts_name[14:] # len("tariff-signal-") is 14
                            _LOGGER.debug("Discovered ZPN: %s", zpn)
                            return zpn
                
                _LOGGER.error("Could not find a valid 'tariff-signal-{ZPN}' in API response. Data: %s", data)
                return None

        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error during setup: %s", err)
            return None
        except Exception as err:
            _LOGGER.exception("Unexpected error during setup: %s", err)
            return None