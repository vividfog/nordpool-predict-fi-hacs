from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Any

from aiohttp import ClientError, ClientResponseError, ContentTypeError
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .const import (
    CONF_INCLUDE_WINDPOWER,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SeriesPoint:
    datetime: datetime
    value: float


HELSINKI_MARKET_RELEASE = time(14, 0)
PREDICTION_START_HOUR = time(1, 0)
HELSINKI_TIMEZONE_NAME = "Europe/Helsinki"


class NordpoolPredictCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches Nordpool FI prediction artifacts."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        base_url: str,
        include_windpower: bool,
        update_interval,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Nordpool Predict FI",
            update_interval=update_interval,
        )
        self.entry_id = entry_id
        self._base_url = base_url or DEFAULT_BASE_URL
        self._include_windpower = include_windpower
        self._helsinki_tz: tzinfo | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def include_windpower(self) -> bool:
        return self._include_windpower

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        now = self._current_time()
        helsinki_tz = self._get_helsinki_timezone()
        helsinki_now = now.astimezone(helsinki_tz)
        release_time = helsinki_now.replace(
            hour=HELSINKI_MARKET_RELEASE.hour,
            minute=HELSINKI_MARKET_RELEASE.minute,
            second=0,
            microsecond=0,
        )
        offset_days = 1 if helsinki_now < release_time else 2
        prediction_start_date = helsinki_now.date() + timedelta(days=offset_days)
        prediction_start_helsinki = datetime.combine(
            prediction_start_date,
            PREDICTION_START_HOUR,
            tzinfo=helsinki_tz,
        )
        prediction_cutoff = prediction_start_helsinki.astimezone(timezone.utc)

        try:
            prediction_rows = await self._fetch_json(session, "prediction.json")
        except FileNotFoundError as err:
            raise UpdateFailed(f"prediction.json missing at {err}") from err
        forecast_series = self._series_from_rows(prediction_rows)

        prediction_points = [point for point in forecast_series if point.datetime >= prediction_cutoff]
        current_point = prediction_points[0] if prediction_points else None

        data: dict[str, Any] = {
            "price": {
                "forecast": prediction_points,
                "current": current_point,
                "now": now,
            },
            "windpower": None,
            "meta": {
                "base_url": self._base_url,
                CONF_INCLUDE_WINDPOWER: self._include_windpower,
                CONF_UPDATE_INTERVAL: self.update_interval,
            },
        }

        if self._include_windpower:
            wind_rows = await self._safe_fetch_optional(session, "windpower.json")
            if wind_rows:
                wind_series = self._series_from_rows(wind_rows)
                prediction_wind = [point for point in wind_series if point.datetime >= prediction_cutoff]
                wind_current = prediction_wind[0] if prediction_wind else None
                data["windpower"] = {
                    "series": prediction_wind,
                    "current": wind_current,
                }

        return data

    async def _safe_fetch_optional(self, session, suffix: str) -> list[Any] | None:
        try:
            return await self._fetch_json(session, suffix)
        except FileNotFoundError:
            _LOGGER.debug("Optional artifact %s not present at %s", suffix, self._compose_url(suffix))
            return None
        except UpdateFailed as err:
            _LOGGER.warning("Could not refresh optional artifact %s: %s", suffix, err)
        except ClientError as err:
            _LOGGER.warning("Network error fetching optional artifact %s: %s", suffix, err)
        except (ContentTypeError, ValueError) as err:
            _LOGGER.warning("Invalid JSON for optional artifact %s: %s", suffix, err)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout reaching optional artifact %s", suffix)
        return None

    async def _fetch_json(self, session, suffix: str) -> list[Any]:
        url = self._compose_url(suffix)
        try:
            async with async_timeout.timeout(20):
                async with session.get(url) as response:
                    try:
                        response.raise_for_status()
                    except ClientResponseError as err:
                        if err.status == 404:
                            raise FileNotFoundError(url) from err
                        raise
                    try:
                        return await response.json(content_type=None)
                    except ValueError as err:
                        raise UpdateFailed(f"Invalid JSON from {url}") from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching {url}") from err
        except ContentTypeError as err:
            raise UpdateFailed(f"Non-JSON response from {url}") from err
        except ClientError as err:
            raise UpdateFailed(f"Network error fetching {url}") from err

    def _compose_url(self, suffix: str) -> str:
        return f"{self._base_url}/{suffix}"

    def _series_from_rows(self, rows: list[Any]) -> list[SeriesPoint]:
        series: list[SeriesPoint] = []
        for row in rows or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            timestamp = self._safe_datetime(row[0])
            value = self._safe_float(row[1])
            if timestamp is None or value is None:
                continue
            series.append(SeriesPoint(datetime=timestamp, value=value))
        series.sort(key=lambda item: item.datetime)
        return series

    @staticmethod
    def _safe_datetime(timestamp: Any) -> datetime | None:
        if timestamp is None:
            return None
        try:
            return datetime.fromtimestamp(float(timestamp) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _current_time() -> datetime:
        return datetime.now(timezone.utc)

    def _get_helsinki_timezone(self) -> tzinfo:
        if self._helsinki_tz is not None:
            return self._helsinki_tz
        try:
            self._helsinki_tz = ZoneInfo(HELSINKI_TIMEZONE_NAME)
        except ZoneInfoNotFoundError as err:
            raise UpdateFailed(
                "Helsinki timezone data is unavailable; install system tzdata to continue."
            ) from err
        return self._helsinki_tz
