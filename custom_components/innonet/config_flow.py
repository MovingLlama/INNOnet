"""Config flow for INNOnet integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, API_BASE_URL, CONF_ZPN

_LOGGER = logging.getLogger(__name__)

# Helper function for discovery (used in ConfigFlow and OptionsFlow)
async def validate_and_discover_zpn(hass: HomeAssistant, api_key: str) -> str | None:
    """Validate API key and discover ZPN."""
    session = async_get_clientsession(hass)
    url = f"{API_BASE_URL}/{api_key}/timeseriescollections/selected-data"
    
    params = {
        "from": "today",
        "to": "today+1d", 
        "datatype": "tariff-signal"
    }

    try:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                _LOGGER.error("INNOnet API returned status %s during discovery", response.status)
                return None
            
            data = await response.json()
            
            # Robust extraction of list items
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                # Check for "Data" (upper) or "data" (lower)
                items = data.get("Data", data.get("data", []))
            
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

    except Exception as err:
        _LOGGER.error("Error during ZPN discovery: %s", err)
        return None


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for INNOnet."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return InnonetOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            manual_zpn = user_input.get(CONF_ZPN)
            
            zpn = None

            if manual_zpn:
                zpn = manual_zpn.strip()
            else:
                zpn = await validate_and_discover_zpn(self.hass, api_key)

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
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_ZPN): str,
            }), 
            errors=errors,
            description_placeholders={
                "zpn_help": "Falls leer gelassen, wird versucht die ZPN automatisch zu finden."
            }
        )


class InnonetOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle INNOnet options (Reconfigure)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            manual_zpn = user_input.get(CONF_ZPN, "").strip()
            
            zpn = None

            if manual_zpn:
                zpn = manual_zpn
            else:
                # If field cleared or empty, try discover with (new) key
                zpn = await validate_and_discover_zpn(self.hass, api_key)

            if zpn:
                # Update the main config entry data
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        CONF_API_KEY: api_key,
                        CONF_ZPN: zpn
                    },
                    title=f"INNOnet ({zpn})"
                )
                return self.async_create_entry(title="", data={})
            else:
                errors["base"] = "discovery_failed"

        # FIX: Ensure we have safe default strings to prevent 500 Error
        current_api_key = self.config_entry.data.get(CONF_API_KEY, "")
        current_zpn = self.config_entry.data.get(CONF_ZPN, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY, default=current_api_key): str,
                vol.Optional(CONF_ZPN, default=current_zpn): str,
            }),
            errors=errors,
            description_placeholders={
                "zpn_help": "Löschen Sie das Feld, um die ZPN erneut automatisch suchen zu lassen."
            }
        )