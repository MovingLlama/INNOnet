"""Konstanten für die INNOnet Integration."""

DOMAIN = "innonet"

# Basis-URL für die API-Anfragen (beide Varianten für Kompatibilität)
BASE_URL = "https://app-innonnetwebtsm-dev.azurewebsites.net/api/extensions/timeseriesauthorization/repositories/INNOnet-prod/apikey"
API_BASE_URL = BASE_URL

# Endpunkt für die ausgewählten Zeitreihendaten
ENDPOINT_SELECTED_DATA = "timeseriescollections/selected-data"

# Konfiguration für die zeitgesteuerte Aktualisierung (10 Sekunden nach der vollen Stunde)
UPDATE_OFFSET_SECONDS = 10
UPDATE_CRON_MINUTE = 0

# Standardwerte für die Persistenz-Logik und Attribute
ATTR_API_ID = "api_id"
ATTR_INTERNAL_NAME = "internal_name"

# Identifikatoren für die Preis-Additionen (Summenbildung)
# Diese MÜSSEN exakt so in const.py vorhanden sein
PRICE_COMPONENT_BASE = "public-energy-tariff-cpid-LZA-tid-LZAPSP"
PRICE_COMPONENT_FEE = "public-energy-tariff-cpid-LZA-tid-LZAPSP-Fee"
PRICE_COMPONENT_VAT = "public-energy-tariff-cpid-LZA-tid-LZAPSP-Vat"

# Name für den berechneten Gesamtpreis-Sensor
CONF_TOTAL_PRICE_NAME = "Gesamtenergiepreis"