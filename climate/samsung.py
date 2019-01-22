"""

Samsung climate platform.

"""

import ipaddress
import requests
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.climate import (
    ClimateDevice, ATTR_TARGET_TEMP_HIGH, ATTR_TARGET_TEMP_LOW,
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_TARGET_HUMIDITY,
    SUPPORT_TARGET_HUMIDITY_LOW, SUPPORT_TARGET_HUMIDITY_HIGH,
    SUPPORT_AWAY_MODE, SUPPORT_HOLD_MODE, SUPPORT_FAN_MODE,
    SUPPORT_OPERATION_MODE, SUPPORT_AUX_HEAT, SUPPORT_SWING_MODE,
    SUPPORT_TARGET_TEMPERATURE_HIGH, SUPPORT_TARGET_TEMPERATURE_LOW,
    SUPPORT_ON_OFF, PLATFORM_SCHEMA)
from homeassistant.const import TEMP_CELSIUS, TEMP_FAHRENHEIT, ATTR_TEMPERATURE, CONF_HOST, CONF_DEVICES, CONF_NAME, CONF_PORT, CONF_TOKEN

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

_LOGGER = logging.getLogger(__name__)
_CERT = '/config/ac14k_m.pem'

def setup_platform(hass, config, add_entities, discovery_info=None):
    
    if CONF_DEVICES not in config:
        return

    devices = config[CONF_DEVICES]

    for device_conf in devices:
        name = device_conf[CONF_NAME]
        host = device_conf[CONF_HOST]
        port = device_conf[CONF_PORT]
        token = device_conf[CONF_TOKEN]

        add_entities([RoomAirConditioner(name, host, port, token)])
    
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
        self._is_on = False
        self._current_mode = ''
        self._current_temperature = None
        self._target_temperature = None
        self._mode_list = ["Heat","Cool","Dry","Wind","Auto"]
        #TODO: wind mode and direction?

        self._support_flags = SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE | SUPPORT_ON_OFF
        self.update()

    def api_put_data(self, path, data):
        requests.put(self._url + path, headers=self._headers, cert=_CERT, data=data, verify=False, timeout=5)

    def update(self):

        req = requests.get(self._url, headers=self._headers, cert=_CERT, verify=False, timeout=5)

        if req.status_code == requests.codes.ok:
            result = req.json()
            if len(result['Devices']) > 0:
                device = result['Devices'][0]
                self._is_on = device["Operation"]["power"] == 'On'
                self._current_mode = device["Mode"]["modes"][0]

                if len(device["Temperatures"]) > 0:
                    temp = device["Temperatures"][0]
                    self._current_temperature = temp["current"]
                    self._target_temperature = temp["desired"]
                    self._temperature_unit = TEMP_CELSIUS if temp["unit"] == 'Celsius' else TEMP_FAHRENHEIT

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    @property
    def should_poll(self):
        """Return the polling state."""
        return True

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._temperature_unit

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
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_mode

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return self._mode_list

    @property
    def is_on(self):
        """Return true if the device is on."""
        return self._is_on

    # @property
    # def current_fan_mode(self):
    #     """Return the fan setting."""
    #     return self._current_fan_mode

    # @property
    # def fan_list(self):
    #     """Return the list of available fan modes."""
    #     return self._fan_list

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            self._target_temperature = kwargs.get(ATTR_TEMPERATURE)

        self.api_put_data('/0/temperatures/0', "{{\"desired\": {} }}".format(self._target_temperature))

    def set_operation_mode(self, operation_mode):
        """Set new target temperature."""
        self._current_mode = operation_mode
        self.api_put_data('/0/mode', "{{\"modes\": [\"{}\"]}}".format(operation_mode))

    def turn_on(self):
        """Turn on."""
        self._is_on = True
        self.api_put_data('/0', "{\"Operation\" : {\"power\" : \"On\"} }")

    def turn_off(self):
        """Turn off."""
        self._is_on = False
        self.api_put_data('/0', "{\"Operation\" : {\"power\" : \"Off\"} }")

    # def set_fan_mode(self, fan_mode):
    #     """Set new target temperature."""
    #     self._current_fan_mode = fan_mode
