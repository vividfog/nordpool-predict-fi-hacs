from datetime import timedelta

#region constants

from homeassistant.const import Platform

#region _core
DOMAIN = "nordpool_predict_fi"
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]

DEFAULT_BASE_URL = "https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy"
SAHKOTIN_BASE_URL = "https://sahkotin.fi/prices.csv"
DEFAULT_UPDATE_INTERVAL_MINUTES = 30
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES)

CONF_BASE_URL = "base_url"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_EXTRA_FEES = "extra_fees"

DATA_COORDINATOR = "coordinator"
DATA_UNSUB_LISTENER = "unsub_listener"

DEFAULT_EXTRA_FEES_CENTS = 0.0
MIN_EXTRA_FEES_CENTS = -200.0
MAX_EXTRA_FEES_CENTS = 200.0
EXTRA_FEES_STEP_CENTS = 0.1

#region _attrs
ATTR_FORECAST = "forecast"
ATTR_FORECAST_START = "forecast_start"
ATTR_RAW_SOURCE = "raw_source"
ATTR_WIND_FORECAST = "windpower_forecast"
ATTR_NEXT_VALID_FROM = "next_valid_from"
ATTR_WINDOW_DURATION = "window_duration_hours"
ATTR_WINDOW_START = "window_start"
ATTR_WINDOW_END = "window_end"
ATTR_WINDOW_POINTS = "window_points"
ATTR_LANGUAGE = "language"
ATTR_NARRATION_CONTENT = "content"
ATTR_NARRATION_SUMMARY = "summary"
ATTR_SOURCE_URL = "source_url"
ATTR_TIMESTAMP = "timestamp"
ATTR_EXTRA_FEES = "extra_fees"
ATTR_DAILY_AVERAGES = "daily_averages"

CHEAPEST_WINDOW_HOURS: tuple[int, ...] = (3, 6, 12)
NEXT_HOURS: tuple[int, ...] = (1, 3, 6, 12)
NARRATION_LANGUAGES: tuple[str, ...] = ("fi", "en")
NARRATION_LANGUAGE_NAMES: dict[str, str] = {
    "fi": "FI",
    "en": "EN",
}
