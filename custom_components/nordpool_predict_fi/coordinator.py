#region setup
from __future__ import annotations

import asyncio
import logging
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time, timezone, tzinfo
from typing import Any, Callable
from urllib.parse import urlencode

from aiohttp import ClientError, ClientResponseError, ContentTypeError
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .const import (
    CHEAPEST_WINDOW_HOURS,
    CONF_EXTRA_FEES,
    CONF_UPDATE_INTERVAL,
    CUSTOM_WINDOW_KEY,
    DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    DEFAULT_CUSTOM_WINDOW_END_HOUR,
    DEFAULT_CUSTOM_WINDOW_HOURS,
    DEFAULT_CUSTOM_WINDOW_START_HOUR,
    DEFAULT_BASE_URL,
    DEFAULT_EXTRA_FEES_CENTS,
    MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    MAX_CUSTOM_WINDOW_HOURS,
    MAX_CUSTOM_WINDOW_HOUR,
    MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    MIN_CUSTOM_WINDOW_HOURS,
    MIN_CUSTOM_WINDOW_HOUR,
    SAHKOTIN_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SeriesPoint:
    datetime: datetime
    value: float


@dataclass(slots=True)
class PriceWindow:
    duration_hours: int
    start: datetime
    end: datetime
    average: float
    points: list[SeriesPoint]


@dataclass(slots=True)
class DailyAverage:
    date: date
    start: datetime
    end: datetime
    average: float
    points: list[SeriesPoint]



HELSINKI_TIMEZONE_NAME = "Europe/Helsinki"


MAX_SUMMARY_LENGTH = 255
SUMMARY_ELLIPSIS = "..."

#region coordinator
class NordpoolPredictCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches Nordpool FI prediction artifacts."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        base_url: str,
        update_interval,
        extra_fees_cents: float | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Nordpool Predict FI",
            update_interval=update_interval,
        )
        self.entry_id = entry_id
        self._base_url = base_url or DEFAULT_BASE_URL
        self._helsinki_tz: tzinfo | None = None
        self._extra_fees_cents = (
            float(extra_fees_cents)
            if extra_fees_cents is not None
            else DEFAULT_EXTRA_FEES_CENTS
        )
        self._custom_window_hours = DEFAULT_CUSTOM_WINDOW_HOURS
        self._custom_window_start_hour = DEFAULT_CUSTOM_WINDOW_START_HOUR
        self._custom_window_end_hour = DEFAULT_CUSTOM_WINDOW_END_HOUR
        self._custom_window_lookahead_hours = DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def extra_fees_cents(self) -> float:
        return self._extra_fees_cents

    def set_extra_fees_cents(self, value: float) -> None:
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            normalized = DEFAULT_EXTRA_FEES_CENTS
        if normalized == self._extra_fees_cents:
            return
        self._extra_fees_cents = normalized
        self.async_update_listeners()

    @property
    def custom_window_hours(self) -> int:
        return self._custom_window_hours

    def set_custom_window_hours(self, value: int) -> None:
        normalized = self._normalize_custom_window_hours(value)
        if normalized == self._custom_window_hours:
            return
        self._custom_window_hours = normalized
        self._rebuild_custom_window_from_cached_data()

    @property
    def custom_window_start_hour(self) -> int:
        return self._custom_window_start_hour

    def set_custom_window_start_hour(self, value: int) -> None:
        normalized = self._normalize_custom_window_hour(value)
        if normalized == self._custom_window_start_hour:
            return
        self._custom_window_start_hour = normalized
        self._rebuild_custom_window_from_cached_data()

    @property
    def custom_window_end_hour(self) -> int:
        return self._custom_window_end_hour

    def set_custom_window_end_hour(self, value: int) -> None:
        normalized = self._normalize_custom_window_hour(value)
        if normalized == self._custom_window_end_hour:
            return
        self._custom_window_end_hour = normalized
        self._rebuild_custom_window_from_cached_data()

    @property
    def custom_window_lookahead_hours(self) -> int:
        return self._custom_window_lookahead_hours

    def set_custom_window_lookahead_hours(self, value: int) -> None:
        normalized = self._normalize_custom_window_lookahead_hours(value)
        if normalized == self._custom_window_lookahead_hours:
            return
        self._custom_window_lookahead_hours = normalized
        self._rebuild_custom_window_from_cached_data()

    @property
    def current_time(self) -> datetime:
        """Provide a testable current time hook.

        Returns UTC now by default. Tests may monkeypatch this attribute on the
        instance to freeze time without touching internal helpers.
        """
        return self._current_time()

    #region _update
    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        now = self._current_time()
        helsinki_tz = self._get_helsinki_timezone()
        helsinki_now = now.astimezone(helsinki_tz)
        
        # Data cutoff: show all data from today midnight Helsinki onwards
        today_midnight_helsinki = helsinki_now.replace(hour=0, minute=0, second=0, microsecond=0)
        data_cutoff = today_midnight_helsinki.astimezone(timezone.utc)
        

        
        try:
            prediction_rows = await self._fetch_json(session, "prediction.json")
        except FileNotFoundError as err:
            raise UpdateFailed(f"prediction.json missing at {err}") from err
        forecast_series = self._series_from_rows(prediction_rows)
        

        
        # Filter forecast to show from today midnight onwards
        forecast_from_today = [
            point for point in forecast_series if point.datetime >= data_cutoff
        ]
        

        
        sahkotin_start_helsinki = helsinki_now.replace(hour=0, minute=0, second=0, microsecond=0)
        sahkotin_start = sahkotin_start_helsinki.astimezone(timezone.utc)
        forecast_horizon = forecast_series[-1].datetime if forecast_series else now + timedelta(days=2)
        sahkotin_end = max(now, forecast_horizon)

        sahkotin_task = asyncio.create_task(
            self._safe_fetch_sahkotin_series(session, sahkotin_start, sahkotin_end)
        )
        narration_fi_task = asyncio.create_task(
            self._safe_fetch_artifact_text(session, "narration.md")
        )
        narration_en_task = asyncio.create_task(
            self._safe_fetch_artifact_text(session, "narration_en.md")
        )

        realized_series = await sahkotin_task
        narration_fi, narration_en = await asyncio.gather(narration_fi_task, narration_en_task)
        

        
        merged_price_series = self._merge_price_series(realized_series, forecast_from_today)
        

        # Find current point from merged series
        current_point = None
        for point in merged_price_series:
            if point.datetime <= now:
                current_point = point
            else:
                break
        
        price_forecast_start = self._forecast_start_from_segments(realized_series, forecast_from_today)
        current_hour_anchor = now.replace(minute=0, second=0, microsecond=0)

        # Calculate cheapest windows using windows that may already be in progress
        cheapest_windows: dict[int, PriceWindow | None] = {}
        for hours in CHEAPEST_WINDOW_HOURS:
            earliest_start = current_hour_anchor - timedelta(hours=hours - 1)
            window = self._find_cheapest_window(
                merged_price_series,
                hours,
                earliest_start=earliest_start,
                min_end=now,
            )
            if window is None:
                window = self._find_cheapest_window(
                    merged_price_series,
                    hours,
                    earliest_start=earliest_start,
                )
            cheapest_windows[hours] = window

        custom_window_entry = self._build_custom_window_entry(
            merged_price_series,
            now,
            helsinki_tz,
        )

        data: dict[str, Any] = {
            "price": {
                "forecast": merged_price_series,
                "current": current_point,
                "cheapest_windows": cheapest_windows,
                "now": now,
                "forecast_start": price_forecast_start,
                CUSTOM_WINDOW_KEY: custom_window_entry,
                "daily_averages": self._calculate_daily_averages(
                    merged_price_series,
                    helsinki_tz,
                ),
            },
            "windpower": None,
            "narration": {
                "fi": self._build_narration_section("narration.md", narration_fi),
                "en": self._build_narration_section("narration_en.md", narration_en),
            },
            "meta": {
                "base_url": self._base_url,
                CONF_UPDATE_INTERVAL: self.update_interval,
                CONF_EXTRA_FEES: self._extra_fees_cents,
            },
        }
        

        
        wind_rows = await self._safe_fetch_artifact(session, "windpower.json")
        if wind_rows:
            wind_series = self._series_from_rows(wind_rows)
            # Filter wind data to show from today midnight onwards
            wind_from_today = [point for point in wind_series if point.datetime >= data_cutoff]
            wind_current = None
            for point in wind_from_today:
                if point.datetime <= now:
                    wind_current = point
                else:
                    break
            data["windpower"] = {
                "series": wind_from_today,
                "current": wind_current,
            }
        

        return data

    #region _fetch
    async def _safe_fetch_artifact(self, session, suffix: str) -> list[Any] | None:
        try:
            return await self._fetch_json(session, suffix)
        except FileNotFoundError:
            _LOGGER.debug("Artifact %s not present at %s", suffix, self._compose_url(suffix))
            return None
        except UpdateFailed as err:
            _LOGGER.warning("Could not refresh artifact %s: %s", suffix, err)
        except ClientError as err:
            _LOGGER.warning("Network error fetching artifact %s: %s", suffix, err)
        except (ContentTypeError, ValueError) as err:
            _LOGGER.warning("Invalid JSON for artifact %s: %s", suffix, err)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout reaching artifact %s", suffix)
        return None

    async def _safe_fetch_artifact_text(self, session, suffix: str) -> str | None:
        try:
            return await self._fetch_text(session, suffix)
        except FileNotFoundError:
            _LOGGER.debug("Artifact %s not present at %s", suffix, self._compose_url(suffix))
            return None
        except UpdateFailed as err:
            _LOGGER.warning("Could not refresh artifact %s: %s", suffix, err)
        except ClientError as err:
            _LOGGER.warning("Network error fetching artifact %s: %s", suffix, err)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout reaching artifact %s", suffix)
        return None

    
    async def _safe_fetch_sahkotin_series(
        self,
        session,
        start: datetime,
        end: datetime,
    ) -> list[SeriesPoint]:
        try:
            csv_text = await self._fetch_sahkotin_csv(session, start, end)
        except UpdateFailed as err:
            _LOGGER.warning("Could not refresh Sähkötin prices: %s", err)
            return []
        except ClientError as err:
            _LOGGER.warning("Network error fetching Sähkötin prices: %s", err)
            return []
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout reaching Sähkötin prices")
            return []

        return self._parse_sahkotin_csv(csv_text, start)

    
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

    
    async def _fetch_text(self, session, suffix: str) -> str:
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
                    return await response.text()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching {url}") from err
        except ClientError as err:
            raise UpdateFailed(f"Network error fetching {url}") from err

    
    async def _fetch_sahkotin_csv(
        self,
        session,
        start: datetime,
        end: datetime,
    ) -> str:
        params = {
            "fix": "true",
            "vat": "true",
            "start": start.replace(microsecond=0).isoformat(),
            "end": end.replace(microsecond=0).isoformat(),
        }
        url = f"{SAHKOTIN_BASE_URL}?{urlencode(params)}"
        try:
            async with async_timeout.timeout(20):
                async with session.get(url) as response:
                    try:
                        response.raise_for_status()
                    except ClientResponseError as err:
                        if err.status == 404:
                            raise UpdateFailed(f"Sähkötin returned 404 for {url}") from err
                        raise UpdateFailed(f"Sähkötin request failed: {err}") from err
                    return await response.text()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching {url}") from err
        except ClientError as err:
            raise UpdateFailed(f"Network error fetching {url}") from err

    
    def _compose_url(self, suffix: str) -> str:
        return f"{self._base_url}/{suffix}"

    #region _parse
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
    #region _time
    def _current_time() -> datetime:
        return datetime.now(timezone.utc)

    #region _custom_window
    def _rebuild_custom_window_from_cached_data(self) -> None:
        data = self.data
        if not isinstance(data, dict):
            self.async_update_listeners()
            return
        price_section = data.get("price")
        if not isinstance(price_section, dict):
            self.async_update_listeners()
            return
        series = price_section.get("forecast")
        if not isinstance(series, list):
            price_section[CUSTOM_WINDOW_KEY] = self._empty_custom_window_entry()
            self.async_update_listeners()
            return
        now = price_section.get("now")
        if not isinstance(now, datetime):
            now = self._current_time()
        helsinki_tz = self._get_helsinki_timezone()
        price_section[CUSTOM_WINDOW_KEY] = self._build_custom_window_entry(series, now, helsinki_tz)
        self.async_update_listeners()

    def _build_custom_window_entry(
        self,
        series: list[SeriesPoint],
        now: datetime,
        helsinki_tz: tzinfo,
    ) -> dict[str, Any]:
        window = self._find_custom_window(series, now, helsinki_tz)
        return {
            "window": window,
            "hours": self._custom_window_hours,
            "start_hour": self._custom_window_start_hour,
            "end_hour": self._custom_window_end_hour,
            "lookahead_hours": self._custom_window_lookahead_hours,
            "lookahead_limit": self._custom_window_lookahead_limit(now),
        }

    def _find_custom_window(
        self,
        series: list[SeriesPoint],
        now: datetime,
        helsinki_tz: tzinfo,
    ) -> PriceWindow | None:
        hours = self._custom_window_hours
        if hours <= 0:
            return None
        mask_hours = self._mask_hours(self._custom_window_start_hour, self._custom_window_end_hour)
        if not mask_hours or hours > len(mask_hours):
            return None
        mask_set = set(mask_hours)
        current_hour_anchor = now.replace(minute=0, second=0, microsecond=0)
        earliest_start = current_hour_anchor - timedelta(hours=hours - 1)
        lookahead_limit = self._custom_window_lookahead_limit(now)

        def _filter(window_points: list[SeriesPoint]) -> bool:
            return self._window_within_mask(window_points, helsinki_tz, mask_set)

        window = self._find_cheapest_window(
            series,
            hours,
            earliest_start=earliest_start,
            min_end=now,
            max_end=lookahead_limit,
            window_filter=_filter,
        )
        if window is None:
            window = self._find_cheapest_window(
                series,
                hours,
                earliest_start=earliest_start,
                max_end=lookahead_limit,
                window_filter=_filter,
            )
        return window

    def _mask_hours(self, start_hour: int, end_hour: int) -> list[int]:
        start = self._normalize_custom_window_hour(start_hour)
        end = self._normalize_custom_window_hour(end_hour)
        if start <= end:
            return list(range(start, end + 1))
        forward = list(range(start, 24))
        backward = list(range(0, end + 1))
        return [*forward, *backward]

    @staticmethod
    def _window_within_mask(
        window_points: list[SeriesPoint],
        helsinki_tz: tzinfo,
        mask_hours: set[int],
    ) -> bool:
        for point in window_points:
            local_hour = point.datetime.astimezone(helsinki_tz).hour
            if local_hour not in mask_hours:
                return False
        return True

    def _normalize_custom_window_hours(self, value: int | float | None) -> int:
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CUSTOM_WINDOW_HOURS
        bounded = max(MIN_CUSTOM_WINDOW_HOURS, min(MAX_CUSTOM_WINDOW_HOURS, coerced))
        return bounded

    def _normalize_custom_window_hour(self, value: int | float | None) -> int:
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CUSTOM_WINDOW_START_HOUR
        bounded = max(MIN_CUSTOM_WINDOW_HOUR, min(MAX_CUSTOM_WINDOW_HOUR, coerced))
        return bounded

    def _normalize_custom_window_lookahead_hours(self, value: int | float | None) -> int:
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS
        bounded = max(
            MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
            min(MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS, coerced),
        )
        return bounded

    def _empty_custom_window_entry(self) -> dict[str, Any]:
        return {
            "window": None,
            "hours": self._custom_window_hours,
            "start_hour": self._custom_window_start_hour,
            "end_hour": self._custom_window_end_hour,
            "lookahead_hours": self._custom_window_lookahead_hours,
            "lookahead_limit": self._custom_window_lookahead_limit(self._current_time()),
        }

    
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

    #region _windows
    def _find_cheapest_window(
        self,
        series: list[SeriesPoint],
        hours: int,
        earliest_start: datetime | None = None,
        min_end: datetime | None = None,
        max_end: datetime | None = None,
        window_filter: Callable[[list[SeriesPoint]], bool] | None = None,
    ) -> PriceWindow | None:
        if hours <= 0 or len(series) < hours:
            return None

        best_window: PriceWindow | None = None
        for index in range(len(series) - hours + 1):
            window_points = series[index : index + hours]
            if not self._is_hourly_sequence(window_points):
                continue
            if window_filter and not window_filter(window_points):
                continue
            start_time = window_points[0].datetime
            if earliest_start and start_time < earliest_start:
                continue
            end_time = window_points[-1].datetime + timedelta(hours=1)
            if min_end and end_time <= min_end:
                continue
            if max_end and end_time > max_end:
                continue
            average = sum(point.value for point in window_points) / hours
            if best_window is None or average < best_window.average:
                best_window = PriceWindow(
                    duration_hours=hours,
                    start=start_time,
                    end=end_time,
                    average=average,
                    points=window_points,
                )
        return best_window

    def _custom_window_lookahead_limit(self, now: datetime) -> datetime:
        anchor = now.replace(minute=0, second=0, microsecond=0)
        return anchor + timedelta(hours=self._custom_window_lookahead_hours)

    @staticmethod
    
    def _is_hourly_sequence(window_points: list[SeriesPoint]) -> bool:
        if len(window_points) <= 1:
            return True
        expected_delta = timedelta(hours=1)
        previous = window_points[0].datetime
        for current in window_points[1:]:
            if current.datetime - previous != expected_delta:
                return False
            previous = current.datetime
        return True

    @staticmethod
    
    def _forecast_start_from_segments(
        realized_series: list[SeriesPoint],
        forecast_series: list[SeriesPoint],
    ) -> datetime | None:
        if not forecast_series:
            return None
        if not realized_series:
            return forecast_series[0].datetime
        last_realized = realized_series[-1].datetime
        for point in forecast_series:
            if point.datetime > last_realized:
                return point.datetime
        return None

    #region _narration
    def _build_narration_section(self, suffix: str, content: str | None) -> dict[str, str] | None:
        if content is None:
            return None
        normalized = content.strip()
        if not normalized:
            return None
        summary = self._build_summary(normalized)
        return {
            "content": normalized,
            "summary": summary,
            "source": self._compose_url(suffix),
        }

    @staticmethod
    
    def _build_summary(content: str) -> str:
        for line in content.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if candidate.startswith("|"):
                continue
            cleaned = candidate.strip("* _")
            compact = " ".join(cleaned.split())
            if len(compact) <= MAX_SUMMARY_LENGTH:
                return compact
            max_content_length = MAX_SUMMARY_LENGTH - len(SUMMARY_ELLIPSIS)
            return f"{compact[:max_content_length].rstrip()}{SUMMARY_ELLIPSIS}"
        return ""

    

    
    def _parse_sahkotin_csv(self, csv_text: str, earliest: datetime | None) -> list[SeriesPoint]:
        if not csv_text:
            return []
        series: list[SeriesPoint] = []
        reader = csv.reader(line for line in csv_text.splitlines() if line)
        header_skipped = False
        for row in reader:
            if not header_skipped:
                header_skipped = True
                continue
            if len(row) < 2:
                continue
            timestamp_raw = row[0].strip()
            price_raw = row[1].strip()
            if not timestamp_raw or not price_raw:
                continue
            timestamp_clean = timestamp_raw.replace("Z", "+00:00").replace(" ", "T")
            try:
                timestamp = datetime.fromisoformat(timestamp_clean)
            except ValueError:
                continue
            # If the parsed timestamp is naive (no tzinfo), treat it as UTC.
            # This is because Sähkötin CSV timestamps are expected to be in UTC if no timezone is specified.
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            value = self._safe_float(price_raw)
            if value is None:
                continue
            timestamp_utc = timestamp.astimezone(timezone.utc)
            if earliest and timestamp_utc < earliest:
                continue
            series.append(SeriesPoint(datetime=timestamp_utc, value=value))
        series.sort(key=lambda item: item.datetime)
        return series

    #region _merge
    def _merge_price_series(
        self,
        realized_series: list[SeriesPoint],
        forecast_series: list[SeriesPoint],
    ) -> list[SeriesPoint]:
        if not realized_series:
            return list(forecast_series)
        merged = list(realized_series)
        last_realized = merged[-1].datetime
        for point in forecast_series:
            if point.datetime <= last_realized:
                continue
            merged.append(point)
        return merged

    def _calculate_daily_averages(
        self,
        series: list[SeriesPoint],
        helsinki_tz: tzinfo,
    ) -> list[DailyAverage]:
        if not series:
            return []

        buckets: dict[date, list[SeriesPoint]] = {}
        for point in series:
            local_dt = point.datetime.astimezone(helsinki_tz)
            buckets.setdefault(local_dt.date(), []).append(point)

        daily: list[DailyAverage] = []
        for local_date in sorted(buckets):
            points = sorted(buckets[local_date], key=lambda item: item.datetime)
            if not self._is_full_helsinki_day(points, helsinki_tz, local_date):
                continue
            average = sum(point.value for point in points) / len(points)
            start_local = datetime.combine(local_date, time(0), tzinfo=helsinki_tz)
            end_local = start_local + timedelta(days=1)
            daily.append(
                DailyAverage(
                    date=local_date,
                    start=start_local,
                    end=end_local,
                    average=average,
                    points=points,
                )
            )
        return daily

    def _is_full_helsinki_day(
        self,
        points: list[SeriesPoint],
        helsinki_tz: tzinfo,
        local_date: date,
    ) -> bool:
        if len(points) != 24:
            return False

        for index, point in enumerate(points):
            local_dt = point.datetime.astimezone(helsinki_tz)
            if local_dt.date() != local_date:
                return False
            if local_dt.hour != index:
                return False
        return True
