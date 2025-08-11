"""Config flow for Samsung Climate integration."""
from __future__ import annotations

import logging
import voluptuous as vol
import ipaddress
import aiohttp
import ssl
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_CERT_PATH

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("port", default="8889"): str,
        vol.Required("token"): str,
        vol.Optional("name", default="Samsung AC"): str,
        vol.Optional("cert_path"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # Validate IP address
    try:
        ipaddress.ip_address(data["host"])
    except ValueError as ex:
        raise InvalidHost from ex

    # Test connection to the device
    try:
        url = f'https://{data["host"]}:{data["port"]}/devices'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {data["token"]}'
        }
        
        async with aiohttp.ClientSession() as session:
            sslcontext = ssl._create_unverified_context()
            if data.get("cert_path"):
                sslcontext.load_cert_chain(data["cert_path"])
            
            async with session.get(url, headers=headers, ssl=sslcontext) as response:
                if response.status != 200:
                    raise CannotConnect
                
                result = await response.json()
                if not result.get('Devices'):
                    raise NoDevices

    except aiohttp.ClientError as ex:
        raise CannotConnect from ex
    except Exception as ex:
        _LOGGER.exception("Unexpected exception")
        raise CannotConnect from ex

    # Return info that you want to store in the config entry.
    return {"title": data["name"]}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Samsung Climate."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidHost:
                errors["host"] = "invalid_host"
            except NoDevices:
                errors["base"] = "no_devices"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create unique ID based on host and port
                unique_id = f"{user_input['host']}_{user_input['port']}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(HomeAssistantError):
    """Error to indicate there is invalid host."""


class NoDevices(HomeAssistantError):
    """Error to indicate no devices found."""
