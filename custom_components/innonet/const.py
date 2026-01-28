"""Konstanten für die INNOnet Integration."""

DOMAIN = "innonet"

# API Konfiguration
BASE_URL = "https://app-innonnetwebtsm-dev.azurewebsites.net/api/extensions/timeseriesauthorization/repositories/INNOnet-prod/apikey"
API_BASE_URL = BASE_URL # Alias für Kompatibilität

# Zeitsteuerung
UPDATE_OFFSET_SECONDS = 10
UPDATE_CRON_MINUTE = 0

# Preis-Komponenten Identifikatoren
PRICE_COMPONENT_ENERGY_PREFIX = "innonet-tariff-"
PRICE_COMPONENT_BASE = "public-energy-tariff-cpid-LZA-tid-LZAPSP"
PRICE_COMPONENT_FEE = "public-energy-tariff-cpid-LZA-tid-LZAPSP-Fee"
PRICE_COMPONENT_VAT = "public-energy-tariff-cpid-LZA-tid-LZAPSP-Vat"

# Signal Identifikator
SIGNAL_TARIFF = "tariff-signal-"