"""Constants for the INNOnet integration."""

DOMAIN = "innonet"
CONF_ZPN = "zpn"

# Base URL as per documentation
# Structure: .../repositories/INNOnet-prod/apikey/{apiKey}/...
API_BASE_URL = "https://app-innonnetwebtsm-dev.azurewebsites.net/api/extensions/timeseriesauthorization/repositories/INNOnet-prod/apikey"

# Update interval in minutes.
# Documentation requires > 5 minutes to avoid overload.
UPDATE_INTERVAL_MINUTES = 15

# Sensor types
SENSOR_TARIFF_SIGNAL = "tariff_signal"
SENSOR_INNONET_TARIFF = "innonet_tariff"
