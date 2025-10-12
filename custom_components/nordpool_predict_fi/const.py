from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "nordpool_predict_fi"
PLATFORMS: list[Platform] = [Platform.SENSOR]

DEFAULT_BASE_URL = "https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy"
DEFAULT_UPDATE_INTERVAL_MINUTES = 30
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES)

CONF_BASE_URL = "base_url"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_INCLUDE_WINDPOWER = "include_windpower"

DATA_COORDINATOR = "coordinator"
DATA_UNSUB_LISTENER = "unsub_listener"

ATTR_FORECAST = "forecast"
ATTR_RAW_SOURCE = "raw_source"
ATTR_WIND_FORECAST = "windpower_forecast"
ATTR_NEXT_VALID_FROM = "next_valid_from"
ATTR_WINDOW_DURATION = "window_duration_hours"
ATTR_WINDOW_START = "window_start"
ATTR_WINDOW_END = "window_end"
ATTR_WINDOW_POINTS = "window_points"

CHEAPEST_WINDOW_HOURS: tuple[int, ...] = (3, 6, 12)
