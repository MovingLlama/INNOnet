"""Config Flow für die INNOnet Integration."""
import logging
import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback

from .const import DOMAIN, API_BASE_URL

_LOGGER = logging.getLogger(__name__)

class InnonetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Behandelt den Konfigurationsfluss für INNOnet."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Erster Schritt bei der manuellen Einrichtung."""
        errors = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            
            # Validierung des API-Keys
            valid = await self._test_api_key(api_key)
            if valid:
                return self.async_create_entry(
                    title=f"INNOnet ({api_key[:8]}...)", 
                    data=user_input
                )
            else:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
            }),
            errors=errors,
        )

    async def _test_api_key(self, api_key):
        """Testet, ob der API-Key gültig ist."""
        # Wir nutzen den Endpunkt für einen Testaufruf
        url = f"{API_BASE_URL}/{api_key}/timeseriescollections/selected-data?from=now&to=now&interval=hour"
        
        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    response = await session.get(url)
                    return response.status == 200
        except Exception:
            return False