"""

Samsung climate platform.

"""

import ipaddress
import asyncio
import aiohttp
import ssl
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.climate import ClimateDevice

from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_FAN,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_OFF,
    SUPPORT_FAN_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_TEMPERATURE_RANGE
)

from homeassistant.const import (
    TEMP_CELSIUS, 
    TEMP_FAHRENHEIT, 
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

DEVICE_CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): vol.All(ipaddress.ip_address, cv.string),
    vol.Optional(CONF_NAME, default='RAC'): cv.string,
    vol.Required(CONF_PORT): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST): cv.string,
    vol.Optional(CONF_DEVICES): vol.All(cv.ensure_list, [DEVICE_CONFIG_SCHEMA]),

})


AC_MODE_TO_HVAC = {
    "auto": HVAC_MODE_HEAT_COOL,
    "cool": HVAC_MODE_COOL,
    "dry": HVAC_MODE_DRY,
    "coolClean": HVAC_MODE_COOL,
    "dryClean": HVAC_MODE_DRY,
    "heat": HVAC_MODE_HEAT,
    "heatClean": HVAC_MODE_HEAT,
    "fanOnly": HVAC_MODE_FAN_ONLY,
    "wind": HVAC_MODE_FAN_ONLY,
}

HVAC_TO_AC_MODE = {
    HVAC_MODE_HEAT_COOL: "auto",
    HVAC_MODE_COOL: "cool",
    HVAC_MODE_DRY: "dry",
    HVAC_MODE_HEAT: "heat",
    HVAC_MODE_FAN_ONLY: "wind",
}

# Only show warnings
#logging.getLogger("urllib3").setLevel(logging.WARNING)
# Disable all child loggers of urllib3, e.g. urllib3.connectionpool
#logging.getLogger("urllib3").propagate = False

_LOGGER = logging.getLogger(__name__)
_CERT = '/mnt/dietpi_userdata/homeassistant/components_configs/ac14k_m.pem'

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    
    if CONF_DEVICES not in config:
        return

    devices = config[CONF_DEVICES]
    entities = []

    for device_conf in devices:
        name = device_conf[CONF_NAME]
        host = device_conf[CONF_HOST]
        port = device_conf[CONF_PORT]
        token = device_conf[CONF_TOKEN]

        entities.append(RoomAirConditioner(name, host, port, token))

    async_add_entities(entities, True)
    
class RoomAirConditioner(ClimateDevice):
    """Representation of a room air conditioner device."""

    def __init__(self, name, host, port, token):
        """Initialize the device."""
        self._name = name
        self._host = host
        self._port = port
        self._token = token
        
        self._url = 'https://{}:{}/devices'.format(host, port)
        self._headers = { 'Content-Type': 'application/json', 'Authorization': 'Bearer {}'.format(token) }
        
        self._temperature_unit = TEMP_CELSIUS
        self._current_temperature = None
        self._target_temperature = None
        self._hvac_mode = HVAC_MODE_OFF;
        self._supported_hvac_modes = [  HVAC_MODE_HEAT_COOL,
                                        HVAC_MODE_COOL,
                                        HVAC_MODE_DRY,
                                        HVAC_MODE_HEAT,
                                        HVAC_MODE_FAN_ONLY,
                                        HVAC_MODE_OFF ];
        

    async def api_put_data(self, path, data):
        async with aiohttp.ClientSession() as session:
            sslcontext = ssl._create_unverified_context()
            sslcontext.load_cert_chain(_CERT)
            await session.put(self._url + path, headers=self._headers, ssl=sslcontext, data=data)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        # OLD VALUES -> SUPPORT_TARGET_TEMPERATURE | ATTR_HVAC_MODE | HVAC_MODE_OFF
        return SUPPORT_TARGET_TEMPERATURE # | SUPPORT_FAN_MODE;

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._temperature_unit

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return self._supported_hvac_modes

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
            self._target_temperature = kwargs.get(ATTR_TEMPERATURE)
            await self.api_put_data('/0/temperatures/0', "{{\"desired\": {} }}".format(self._target_temperature))
        
        self.async_schedule_update_ha_state(True)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new operation mode."""
        if self._hvac_mode == hvac_mode:
            return
        
        self._hvac_mode = hvac_mode
        
        if hvac_mode == HVAC_MODE_OFF:
            await self.api_put_data('/0', "{\"Operation\" : {\"power\" : \"Off\"} }")
        else:
            ac_mode = HVAC_TO_AC_MODE[hvac_mode]
            await self.api_put_data('/0', "{{\"Operation\" : {{\"power\" : \"On\"}}, \"Mode\" : {{\"modes\": [\"{}\"] }}}}".format(ac_mode.capitalize()))
        
        self.async_schedule_update_ha_state(True)
    
    async def async_update(self):
        async with aiohttp.ClientSession() as session:
            sslcontext = ssl._create_unverified_context()
            sslcontext.load_cert_chain(_CERT)
            async with session.get(self._url, headers=self._headers, ssl=sslcontext) as r:            
                if r.status == 200:
                    result = await r.json()
                    if len(result['Devices']) > 0:
                        device = result['Devices'][0]
                        if device["Operation"]["power"] == 'On':
                            self._hvac_mode = AC_MODE_TO_HVAC.get(device["Mode"]["modes"][0].lower())
                        else:
                            self._hvac_mode = HVAC_MODE_OFF

                        if len(device["Temperatures"]) > 0:
                            temp = device["Temperatures"][0]
                            self._current_temperature = temp["current"]
                            self._target_temperature = temp["desired"]
                            self._temperature_unit = TEMP_CELSIUS if temp["unit"] == 'Celsius' else TEMP_FAHRENHEIT
