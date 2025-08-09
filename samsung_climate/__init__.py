"""Samsung Climate integration for Home Assistant."""

from homeassistant.const import Platform

DOMAIN = "samsung_climate"
PLATFORMS = [Platform.CLIMATE]

async def async_setup(hass, config):
    """Set up the Samsung Climate component."""
    return True

async def async_setup_entry(hass, entry):
    """Set up Samsung Climate from a config entry."""
    return True
