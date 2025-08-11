"""Constants for the Samsung Climate integration."""
from homeassistant.const import Platform

DOMAIN = "samsung_climate"
PLATFORMS = [Platform.CLIMATE]

# Configuration constants
CONF_CERT_PATH = "cert_path"
DEFAULT_CERT_PATH = "ac14k_m.pem"  # Default certificate filename within the component
