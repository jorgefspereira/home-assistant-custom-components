"""Samsung climate platform for Home Assistant."""

import ssl
import logging
import os
import json
import asyncio

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

from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

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

    # Create a coordinator for polling
    async def async_update_data():
        """Fetch data from API (this is the polling function)."""
        _LOGGER.warning("Coordinator polling state for %s", name)
        result = await _http_request(hass, host, port, token, cert_path)  # We'll define this helper below
        if result and len(result.get('Devices', [])) > 0:
            return result['Devices'][0]  # Return the device data
        return None  # Or raise CoordinatorUpdateError if you want HA to handle retries

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{config_entry.entry_id}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=1),  # Poll every 1 minute (adjust as needed; e.g., 5 for less frequent)
    )

    # Refresh once on setup to get initial state
    await coordinator.async_config_entry_first_refresh()

    entity = RoomAirConditioner(
        coordinator=coordinator,  # Pass coordinator to entity
        name=name,
        host=host,
        port=port,
        token=token,
        cert_path=cert_path,
        unique_id=config_entry.entry_id
    )
    async_add_entities([entity], True)

# Helper function to avoid duplicating _http_request logic (extracted from your class)
async def _http_request(hass, host, port, token, cert_path, method="GET", path="", data=None):
    """Shared HTTP request logic (extracted for coordinator use)."""
    # (Copy your existing _http_request implementation here, but make it a standalone async function.
    # Remove self-references; use passed params instead. For example:)
    try:
        def create_ssl_context():
            sslcontext = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            sslcontext.set_ciphers('DEFAULT:@SECLEVEL=0')
            sslcontext.check_hostname = False
            sslcontext.verify_mode = ssl.CERT_NONE
            sslcontext.minimum_version = ssl.TLSVersion.TLSv1
            sslcontext.maximum_version = ssl.TLSVersion.TLSv1_3
            sslcontext.options |= ssl.OP_LEGACY_SERVER_CONNECT
            try:
                sslcontext.load_cert_chain(cert_path)
            except ssl.SSLError as ssl_ex:
                _LOGGER.warning("SSL certificate load failed: %s", ssl_ex)
            return sslcontext
        
        sslcontext = await hass.async_add_executor_job(create_ssl_context)
        
        reader, writer = await asyncio.open_connection(host, int(port), ssl=sslcontext)
        
        request = f"{method} /devices{path} HTTP/1.1\r\n"
        request += f"Host: {host}:{port}\r\n"
        request += f"Authorization: Bearer {token}\r\n"
        
        if method == "PUT" and data:
            request += f"Content-Length: {len(data)}\r\n"
            request += "Content-Type: application/json\r\n"
        
        request += "Connection: close\r\n"
        request += "\r\n"
        
        if method == "PUT" and data:
            request += data
        
        writer.write(request.encode())
        await writer.drain()
        
        response_data = await reader.read()
        writer.close()
        await writer.wait_closed()
        
        response_text = response_data.decode('utf-8', errors='ignore')
        
        if "HTTP/1.1 200" in response_text or "HTTP/1.1 204" in response_text:
            if method == "PUT":
                return True
            else:
                json_start = response_text.find('\r\n\r\n')
                if json_start != -1:
                    json_data = response_text[json_start + 4:]
                    if json_data.strip():
                        return json.loads(json_data)
        return None
    
    except Exception as ex:
        _LOGGER.error("HTTP request failed: %s", ex)
        return None


class RoomAirConditioner(CoordinatorEntity, ClimateEntity):  # Inherit from CoordinatorEntity
    """Representation of a room air conditioner device."""
    
    def __init__(self, coordinator, name, host, port, token, cert_path, unique_id):  # Add coordinator param
        """Initialize the device."""
        super().__init__(coordinator)  # Initialize coordinator
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
        self._attr_should_poll = False  # Disable automatic polling

    # (Keep your properties like supported_features, temperature_unit, etc., as-is)

    async def async_added_to_hass(self):
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()  # Initial update from coordinator data

    def _handle_coordinator_update(self):
        """Update entity from coordinator data (called on poll)."""
        device = self.coordinator.data
        if device:
            if device["Operation"]["power"] == 'On':
                self._attr_hvac_mode = AC_MODE_TO_HVAC.get(
                    device["Mode"]["modes"][0].lower(), 
                    HVACMode.OFF
                )
            else:
                self._attr_hvac_mode = HVACMode.OFF
            if len(device.get("Temperatures", [])) > 0:
                temp = device["Temperatures"][0]
                _LOGGER.warning("Updated temperature to B1 %s", temp["desired"])
                self._attr_current_temperature = temp["current"]
                self._attr_target_temperature = temp["desired"]
                self._attr_temperature_unit = (
                    UnitOfTemperature.CELSIUS 
                    if temp["unit"] == 'Celsius' 
                    else UnitOfTemperature.FAHRENHEIT
                )
        self.async_write_ha_state()  # Push to HA

    # Remove your existing async_update (coordinator handles polling now)

    async def api_put_data(self, path, data):
        """Send PUT request to the device API."""
        return await _http_request(  # Use shared helper
            self.hass, self._host, self._port, self._token, self._cert_path,
            method="PUT", path=path, data=data
        )

    # Update service methods to trigger coordinator refresh after a delay
    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            target_temp = kwargs.get(ATTR_TEMPERATURE)
            _LOGGER.warning("Updated temperature to A1 %s", target_temp)
            success = await self.api_put_data(
                '/0/temperatures/0', 
                f'{{"desired": {target_temp} }}'
            )
            if success:
                _LOGGER.warning("Updated temperature to A2 %s", target_temp)
                self._attr_target_temperature = target_temp
                self.async_write_ha_state()  # Optimistic push
                
                # Schedule a poll after delay to confirm (avoids race with stale API data)
                await asyncio.sleep(5)  # Adjust delay based on your API's update time (e.g., 5-10 sec)
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to set temperature for %s", self._name)
    
    async def async_set_hvac_mode(self, hvac_mode):
        """Set new operation mode."""
        if self._attr_hvac_mode == hvac_mode:
            return
        
        success = False
        
        if hvac_mode == HVACMode.OFF:
            success = await self.api_put_data('/0', '{"Operation" : {"power" : "Off"} }')
        else:
            ac_mode = HVAC_TO_AC_MODE[hvac_mode]
            success = await self.api_put_data(
                '/0', 
                f'{{"Operation" : {{"power" : "On"}}, "Mode" : {{"modes": ["{ac_mode.capitalize()}"] }}}}'
            )
        
        if success:
            self._attr_hvac_mode = hvac_mode
            self.async_write_ha_state()  # Optimistic push
            
            # Schedule a poll after delay to confirm
            await asyncio.sleep(5)  # Adjust as needed
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set HVAC mode for %s", self._name)

    # (Remove your _http_request from the class; use the shared one)