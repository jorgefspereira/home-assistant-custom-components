"""Config flow for Samsung Climate integration."""
from __future__ import annotations

import logging
import voluptuous as vol
import ipaddress
import aiohttp
import ssl
import os
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
        vol.Required("port", default="8887"): str,
        vol.Required("token"): str,
        vol.Optional("name", default="Samsung AC"): str,
        vol.Optional("cert_path", default="ac14k_m.pem"): str,
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

    # Get the certificate path - if relative, make it relative to this component
    cert_path = data.get("cert_path", "ac14k_m.pem")
    if not os.path.isabs(cert_path):
        # Get the directory where this integration is located
        component_dir = os.path.dirname(os.path.abspath(__file__))
        cert_path = os.path.join(component_dir, cert_path)
    
    # Check if certificate file exists
    if not os.path.exists(cert_path):
        raise CertificateNotFound

    # Test connection to the device
    try:
        url = f'https://{data["host"]}:{data["port"]}/devices'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {data["token"]}',
            'X-API-Version': 'v1.0.0'
        }
        
        # Create SSL context in executor to avoid blocking
        def create_ssl_context():
            sslcontext = ssl._create_unverified_context()
            # Allow weak certificates and signatures for older devices
            sslcontext.set_ciphers('DEFAULT:@SECLEVEL=0')
            sslcontext.check_hostname = False
            sslcontext.verify_mode = ssl.CERT_NONE
            
            # Enable older TLS versions for compatibility with old devices
            sslcontext.minimum_version = ssl.TLSVersion.TLSv1
            sslcontext.maximum_version = ssl.TLSVersion.TLSv1_3
            
            # Set additional options for compatibility
            sslcontext.options |= ssl.OP_LEGACY_SERVER_CONNECT
            
            try:
                sslcontext.load_cert_chain(cert_path)
            except ssl.SSLError as ssl_ex:
                _LOGGER.warning("SSL certificate load failed: %s", ssl_ex)
                # Continue without client certificate if loading fails
                pass
            return sslcontext
        
        # Run SSL context creation in executor
        sslcontext = await hass.async_add_executor_job(create_ssl_context)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, ssl=sslcontext) as response:
                    if response.status != 200:
                        print(f"Failed to connect AA to {data['host']}:{data['port']}")
                        raise CannotConnect
                    
                    result = await response.json()
                    if not result.get('Devices'):
                        raise NoDevices
            except (aiohttp.ClientSSLError, ssl.SSLError) as ssl_error:
                _LOGGER.warning("SSL connection failed, trying without SSL: %s", ssl_error)
                # Try without SSL as fallback
                url_no_ssl = f'http://{data["host"]}:{data["port"]}/devices'
                async with session.get(url_no_ssl, headers=headers) as response:
                    if response.status != 200:
                        raise CannotConnect
                    
                    result = await response.json()
                    if not result.get('Devices'):
                        raise NoDevices

    except FileNotFoundError as ex:
        raise CertificateNotFound from ex
    except aiohttp.ClientError as ex:
        print(f"Failed to connect BB to {ex}")
        raise CannotConnect from ex
    except Exception as ex:
        print(f"Failed to connect CC to {data['host']}:{data['port']}")
        _LOGGER.exception("Unexpected exception")
        raise CannotConnect from ex

    # Store the full path for later use
    data["cert_path"] = cert_path
    
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
            except CertificateNotFound:
                errors["cert_path"] = "certificate_not_found"
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


class CertificateNotFound(HomeAssistantError):
    """Error to indicate certificate file not found."""
