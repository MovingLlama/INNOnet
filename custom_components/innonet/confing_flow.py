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

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
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
            api_key = user_input[CONF_API_KEY]
            
            # Validate the API key and try to auto-discover the ZPN (Metering Point Number)
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
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def _validate_and_discover_zpn(self, api_key: str) -> str | None:
        """
        Validate API key and discover ZPN.
        
        We query the 'selected-data' endpoint for the 'tariff-signal'.
        The response usually contains the timeseries name in the format 'tariff-signal-{ZPN}'.
        This allows us to extract the ZPN automatically.
        """
        session = async_get_clientsession(self.hass)
        # URL to fetch metadata about the tariff signal to find the user's ZPN
        url = f"{API_BASE_URL}/{api_key}/timeseriescollections/selected-data"
        params = {
            "from": "today",
            "to": "today",
            "datatype": "tariff-signal"
        }

        try:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    _LOGGER.error("INNOnet API returned status %s during setup", response.status)
                    return None
                
                data = await response.json()
                
                # Check if we got a list and it's not empty
                if isinstance(data, list) and len(data) > 0:
                    # Look for the first entry that looks like a tariff signal
                    for item in data:
                        ts_name = item.get("name", "")
                        if ts_name.startswith("tariff-signal-"):
                            # Extract ZPN: "tariff-signal-123456" -> "123456"
                            zpn = ts_name.replace("tariff-signal-", "")
                            _LOGGER.debug("Discovered ZPN: %s", zpn)
                            return zpn
                
                _LOGGER.error("Could not find a valid 'tariff-signal-{ZPN}' in API response.")
                return None

        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error during setup: %s", err)
            return None
        except Exception as err:
            _LOGGER.exception("Unexpected error during setup: %s", err)
            return None