"""Konstanten für die INNOnet Integration."""

DOMAIN = "innonet"

# Basis-URL für die API-Anfragen
BASE_URL = "https://app-innonnetwebtsm-dev.azurewebsites.net/api/extensions/timeseriesauthorization/repositories/INNOnet-prod/apikey"
API_BASE_URL = BASE_URL

# Endpunkt für die ausgewählten Zeitreihendaten
ENDPOINT_SELECTED_DATA = "timeseriescollections/selected-data"

# Konfiguration für die zeitgesteuerte Aktualisierung (10 Sekunden nach der vollen Stunde)
UPDATE_OFFSET_SECONDS = 10
UPDATE_CRON_MINUTE = 0

# Identifikatoren für die Preis-Additionen (Summenbildung)
# Mappings für die gewünschten Namen
NAME_MAPPING = {
    "innonet-tariff-": "Energy Price",
    "public-energy-tariff-cpid-LZA-tid-LZAPSP": "Grid Price",
    "public-energy-tariff-cpid-LZA-tid-LZAPSP-Fee": "Grid Fee",
    "public-energy-tariff-cpid-LZA-tid-LZAPSP-Vat": "Grid VAT",
    "tariff-signal-": "Tariff Signal"
}

# Preiskomponenten für die Summe (Total Price)
PRICE_COMPONENT_ENERGY_PREFIX = "innonet-tariff-"
PRICE_COMPONENT_BASE = "public-energy-tariff-cpid-LZA-tid-LZAPSP"
PRICE_COMPONENT_FEE = "public-energy-tariff-cpid-LZA-tid-LZAPSP-Fee"
PRICE_COMPONENT_VAT = "public-energy-tariff-cpid-LZA-tid-LZAPSP-Vat"

# Name für den berechneten Gesamtpreis-Sensor
CONF_TOTAL_PRICE_NAME = "Total Price"