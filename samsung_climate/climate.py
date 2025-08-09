"""Samsung climate platform for Home Assistant."""

import ipaddress
import asyncio
import aiohttp
import ssl
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.climate import ClimateEntity

from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    HVACAction,
    HVACMode,
    ClimateEntityFeature
)

from homeassistant.const import (
    UnitOfTemperature, 
    ATTR_TEMPERATURE, 
    CONF_HOST, 
    CONF_DEVICES, 
    CONF_NAME, 
    CONF_PORT, 
    CONF_TOKEN
)

from homeassistant.helpers.config_validation import (
    PLATFORM_SCHEMA, 
    PLATFORM_SCHEMA_BASE
)

# Configuration constants
CONF_CERT_PATH = "cert_path"

DEVICE_CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): vol.All(ipaddress.ip_address, cv.string),
    vol.Optional(CONF_NAME, default='RAC'): cv.string,
    vol.Required(CONF_PORT): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
    vol.Optional(CONF_CERT_PATH): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST): cv.string,
    vol.Optional(CONF_DEVICES): vol.All(cv.ensure_list, [DEVICE_CONFIG_SCHEMA]),
})


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

# Only show warnings
#logging.getLogger("urllib3").setLevel(logging.WARNING)
# Disable all child loggers of urllib3, e.g. urllib3.connectionpool
#logging.getLogger("urllib3").propagate = False

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Samsung climate platform."""
    if CONF_DEVICES not in config:
        _LOGGER.error("No devices configured")
        return

    devices = config[CONF_DEVICES]
    entities = []

    for device_conf in devices:
        name = device_conf[CONF_NAME]
        host = device_conf[CONF_HOST]
        port = device_conf[CONF_PORT]
        token = device_conf[CONF_TOKEN]
        cert_path = device_conf[CONF_CERT_PATH]

        entities.append(RoomAirConditioner(name, host, port, token, cert_path))

    async_add_entities(entities, True)
    
class RoomAirConditioner(ClimateEntity):
    """Representation of a room air conditioner device."""

    def __init__(self, name, host, port, token, cert_path):
        """Initialize the device."""
        self._name = name
        self._host = host
        self._port = port
        self._token = token
        self._cert_path = cert_path
        
        self._url = f'https://{host}:{port}/devices'
        self._headers = { 
            'Content-Type': 'application/json', 
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
    async def api_put_data(self, path, data):
        """Send PUT request to the device API."""
        try:
            async with aiohttp.ClientSession() as session:
                sslcontext = ssl._create_unverified_context()
                sslcontext.load_cert_chain(self._cert_path)
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
            async with aiohttp.ClientSession() as session:
                sslcontext = ssl._create_unverified_context()
                sslcontext.load_cert_chain(self._cert_path)
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
        except Exception as ex:
            _LOGGER.error("Error updating %s: %s", self._name, ex)
