"""Samsung climate platform for Home Assistant."""

import aiohttp
import ssl
import logging
import os

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACAction,
    HVACMode,
    ClimateEntityFeature
)
from homeassistant.const import (
    UnitOfTemperature, 
    ATTR_TEMPERATURE
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_CERT_PATH, DEFAULT_CERT_PATH


_LOGGER = logging.getLogger(__name__)

AC_MODE_TO_HVAC = {
    "auto": HVACMode.HEAT_COOL,
    "cool": HVACMode.COOL,
    "dry": HVACMode.DRY,
    "coolClean": HVACMode.COOL,
    "dryClean": HVACMode.DRY,
    "heat": HVACMode.HEAT,
    "heatClean": HVACMode.HEAT,
    "fanOnly": HVACMode.FAN_ONLY,
    "wind": HVACMode.FAN_ONLY,
}

HVAC_TO_AC_MODE = {
    HVACMode.HEAT_COOL: "auto",
    HVACMode.COOL: "cool",
    HVACMode.DRY: "dry",
    HVACMode.HEAT: "heat",
    HVACMode.FAN_ONLY: "wind",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Samsung climate platform from config entry."""
    data = config_entry.data
    
    name = data.get("name", "Samsung AC")
    host = data["host"]
    port = data["port"]
    token = data["token"]
    cert_path = data.get("cert_path", "ac14k_m.pem")
    
    # If cert_path is relative, make it relative to this component directory
    if not os.path.isabs(cert_path):
        component_dir = os.path.dirname(os.path.abspath(__file__))
        cert_path = os.path.join(component_dir, cert_path)

    entity = RoomAirConditioner(
        name=name,
        host=host,
        port=port,
        token=token,
        cert_path=cert_path,
        unique_id=config_entry.entry_id
    )

    async_add_entities([entity], True)
class RoomAirConditioner(ClimateEntity):
    """Representation of a room air conditioner device."""

    def __init__(self, name, host, port, token, cert_path, unique_id):
        """Initialize the device."""
        self._name = name
        self._host = host
        self._port = port
        self._token = token
        self._cert_path = cert_path
        self._attr_unique_id = unique_id
        
        self._url = f'https://{host}:{port}/devices'
        self._headers = { 
            'Authorization': f'Bearer {token}'
        }
        
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_modes = [
            HVACMode.HEAT_COOL,
            HVACMode.COOL,
            HVACMode.DRY,
            HVACMode.HEAT,
            HVACMode.FAN_ONLY,
            HVACMode.OFF
        ]
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    async def _raw_http_request(self):
        """Fallback method using raw HTTP to handle malformed headers."""
        import json
        import asyncio
        
        try:
            # Use asyncio to create a raw connection
            reader, writer = await asyncio.open_connection(
                self._host, int(self._port), ssl=True
            )
            
            # Construct manual HTTP request
            request = f"GET /devices HTTP/1.1\r\n"
            request += f"Host: {self._host}:{self._port}\r\n"
            request += f"Authorization: Bearer {self._token}\r\n"
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
            
            # Find the JSON part (after the headers)
            json_start = response_text.find('\r\n\r\n')
            if json_start != -1:
                json_data = response_text[json_start + 4:]
                result = json.loads(json_data)
                
                # Process the data same as before
                if len(result.get('Devices', [])) > 0:
                    device = result['Devices'][0]
                    if device["Operation"]["power"] == 'On':
                        self._attr_hvac_mode = AC_MODE_TO_HVAC.get(
                            device["Mode"]["modes"][0].lower(), 
                            HVACMode.OFF
                        )
                    else:
                        self._attr_hvac_mode = HVACMode.OFF

                    if len(device.get("Temperatures", [])) > 0:
                        temp = device["Temperatures"][0]
                        self._attr_current_temperature = temp["current"]
                        self._attr_target_temperature = temp["desired"]
                        self._attr_temperature_unit = (
                            UnitOfTemperature.CELSIUS 
                            if temp["unit"] == 'Celsius' 
                            else UnitOfTemperature.FAHRENHEIT
                        )
                    
                    _LOGGER.info("Successfully updated %s using raw HTTP", self._name)
                    
        except Exception as ex:
            _LOGGER.error("Raw HTTP request failed for %s: %s", self._name, ex)
        
    async def api_put_data(self, path, data):
        """Send PUT request to the device API."""
        try:
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
                    sslcontext.load_cert_chain(self._cert_path)
                except ssl.SSLError as ssl_ex:
                    _LOGGER.warning("SSL certificate load failed for %s: %s", self._name, ssl_ex)
                    # Continue without client certificate if loading fails
                    pass
                return sslcontext
            
            # Run SSL context creation in executor
            sslcontext = await self.hass.async_add_executor_job(create_ssl_context)
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.put(
                        self._url + path, 
                        headers=self._headers, 
                        ssl=sslcontext, 
                        data=data
                    ) as response:
                        if response.status != 200:
                            _LOGGER.error(
                                "Failed to send command to %s: %s", 
                                self._name, 
                                response.status
                            )
                except aiohttp.ClientResponseError as resp_error:
                    if "Invalid header token" in str(resp_error):
                        _LOGGER.warning("Server sent malformed headers for %s during command, but command may have succeeded", self._name)
                        # Server responded but with malformed headers - command might have worked
                        # We can't verify the response but the device is responding
                    else:
                        _LOGGER.error("Response error for %s: %s", self._name, resp_error)
                        raise
        except Exception as ex:
            _LOGGER.error("Error communicating with %s: %s", self._name, ex)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._attr_supported_features

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._attr_temperature_unit

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._attr_current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._attr_target_temperature

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self._attr_hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return self._attr_hvac_modes

    # @property
    # def fan_mode(self):
    #     """Return the fan setting."""
    #     return self._device.status.fan_mode

    # @property
    # def fan_modes(self):
    #     """Return the list of available fan modes."""
    #     return self._device.status.supported_ac_fan_modes


    ######################################################################
    #
    # Async methods
    #
    #######################################################################

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            self._attr_target_temperature = kwargs.get(ATTR_TEMPERATURE)
            await self.api_put_data(
                '/0/temperatures/0', 
                f'{{"desired": {self._attr_target_temperature} }}'
            )
        
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new operation mode."""
        if self._attr_hvac_mode == hvac_mode:
            return
        
        self._attr_hvac_mode = hvac_mode
        
        if hvac_mode == HVACMode.OFF:
            await self.api_put_data('/0', '{"Operation" : {"power" : "Off"} }')
        else:
            ac_mode = HVAC_TO_AC_MODE[hvac_mode]
            await self.api_put_data(
                '/0', 
                f'{{"Operation" : {{"power" : "On"}}, "Mode" : {{"modes": ["{ac_mode.capitalize()}"] }}}}'
            )
        
        self.async_write_ha_state()
    
    async def async_update(self):
        """Fetch new state data for this climate device."""
        try:
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
                    sslcontext.load_cert_chain(self._cert_path)
                except ssl.SSLError as ssl_ex:
                    _LOGGER.warning("SSL certificate load failed for %s: %s", self._name, ssl_ex)
                    # Continue without client certificate if loading fails
                    pass
                return sslcontext
            
            # Run SSL context creation in executor
            sslcontext = await self.hass.async_add_executor_job(create_ssl_context)
            
            # Try to get data with aiohttp, fallback to manual parsing if headers fail
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self._url, 
                        headers=self._headers, 
                        ssl=sslcontext
                    ) as response:            
                        if response.status == 200:
                            result = await response.json()
                            if len(result.get('Devices', [])) > 0:
                                device = result['Devices'][0]
                                if device["Operation"]["power"] == 'On':
                                    self._attr_hvac_mode = AC_MODE_TO_HVAC.get(
                                        device["Mode"]["modes"][0].lower(), 
                                        HVACMode.OFF
                                    )
                                else:
                                    self._attr_hvac_mode = HVACMode.OFF

                                if len(device.get("Temperatures", [])) > 0:
                                    temp = device["Temperatures"][0]
                                    self._attr_current_temperature = temp["current"]
                                    self._attr_target_temperature = temp["desired"]
                                    self._attr_temperature_unit = (
                                        UnitOfTemperature.CELSIUS 
                                        if temp["unit"] == 'Celsius' 
                                        else UnitOfTemperature.FAHRENHEIT
                                    )
                        else:
                            _LOGGER.error(
                                "Failed to update %s: HTTP %s", 
                                self._name, 
                                response.status
                            )
            except aiohttp.ClientResponseError as resp_error:
                if "Invalid header token" in str(resp_error):
                    _LOGGER.warning("Malformed headers from %s, attempting raw HTTP request", self._name)
                    # Try with a more basic approach using raw socket connection
                    await self._raw_http_request()
                else:
                    _LOGGER.error("Response error for %s: %s", self._name, resp_error)
                    raise
        except Exception as ex:
            _LOGGER.error("Error updating %s: %s", self._name, ex)
