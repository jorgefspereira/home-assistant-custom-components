"""Config flow for Samsung Climate integration."""
from __future__ import annotations

import logging
import voluptuous as vol
import ipaddress
import ssl
import os
import asyncio
import json
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
        vol.Required("port", default="8888"): str,
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
        # Create SSL context in executor to avoid blocking
        def create_ssl_context():
            # Use SSLContext constructor directly to avoid set_default_verify_paths
            sslcontext = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
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
        
        # Use raw HTTP to avoid malformed header issues
        reader, writer = await asyncio.open_connection(
            data["host"], int(data["port"]), ssl=sslcontext
        )
        
        # Construct manual HTTP request
        request = f"GET /devices HTTP/1.1\r\n"
        request += f"Host: {data['host']}:{data['port']}\r\n"
        request += f"Authorization: Bearer {data['token']}\r\n"
        request += "Connection: close\r\n"
        request += "\r\n"
        
        writer.write(request.encode())
        await writer.drain()
        
        # Read the response
        response_data = await reader.read()
        writer.close()
        await writer.wait_closed()
        
        # Parse the response manually
        response_text = response_data.decode('utf-8', errors='ignore')
        
        # Check if we got a 200 response
        if "HTTP/1.1 200" not in response_text:
            raise CannotConnect
        
        # Find the JSON part (after the headers)
        json_start = response_text.find('\r\n\r\n')
        if json_start != -1:
            json_data = response_text[json_start + 4:]
            if json_data.strip():
                result = json.loads(json_data)
                if not result.get('Devices'):
                    raise NoDevices

    except FileNotFoundError as ex:
        raise CertificateNotFound from ex
    except (ConnectionError, OSError, asyncio.TimeoutError) as ex:
        raise CannotConnect from ex
    except Exception as ex:
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
