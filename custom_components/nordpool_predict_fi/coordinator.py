#region setup
from __future__ import annotations

import asyncio
import logging
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, ClientResponseError, ContentTypeError
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .const import CHEAPEST_WINDOW_HOURS, CONF_UPDATE_INTERVAL, DEFAULT_BASE_URL, SAHKOTIN_BASE_URL

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

    @property
    def base_url(self) -> str:
        return self._base_url

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
        

        # Calculate cheapest windows using the full merged series
        cheapest_windows = {
            hours: self._find_cheapest_window(merged_price_series, hours)
            for hours in CHEAPEST_WINDOW_HOURS
        }
        

        
        data: dict[str, Any] = {
            "price": {
                "forecast": merged_price_series,
                "current": current_point,
                "cheapest_windows": cheapest_windows,
                "now": now,
            },
            "windpower": None,
            "narration": {
                "fi": self._build_narration_section("narration.md", narration_fi),
                "en": self._build_narration_section("narration_en.md", narration_en),
            },
            "meta": {
                "base_url": self._base_url,
                CONF_UPDATE_INTERVAL: self.update_interval,
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
    ) -> PriceWindow | None:
        if hours <= 0 or len(series) < hours:
            return None

        best_window: PriceWindow | None = None
        for index in range(len(series) - hours + 1):
            window_points = series[index : index + hours]
            if not self._is_hourly_sequence(window_points):
                continue
            average = sum(point.value for point in window_points) / hours
            if best_window is None or average < best_window.average:
                start_time = window_points[0].datetime
                end_time = window_points[-1].datetime + timedelta(hours=1)
                best_window = PriceWindow(
                    duration_hours=hours,
                    start=start_time,
                    end=end_time,
                    average=average,
                    points=window_points,
                )
        return best_window

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

    #region _narration
    def _build_narration_section(self, suffix: str, content: str | None) -> dict[str, str] | None:
        if content is None:
            return None
        normalized = content.strip()
        if not normalized:
            return None
        summary = self._build_summary(normalized)
        table = self._extract_first_table(normalized) or ""
        return {
            "content": normalized,
            "summary": summary,
            "table": table,
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

    @staticmethod
    def _extract_first_table(content: str) -> str | None:
        """Return the first well-formed Markdown table (header + alignment + rows).

        A Markdown table is detected by:
        - header line: starts with '|', and contains at least one column separator
        - alignment line: the next non-empty line consists of pipes with `-` and optional `:`
        - data rows: contiguous lines starting with '|' (allowing spaces) until a non-table line

        This avoids accidentally capturing stray lines that begin with '|' but are not tables,
        and stops precisely at the end of the table block.
        """
        lines = content.splitlines()

        def is_table_header(line: str) -> bool:
            s = line.lstrip()
            if not s.startswith("|"):
                return False
            # Header should have at least two pipes to imply two columns
            return s.count("|") >= 2

        def is_alignment(line: str) -> bool:
            s = line.strip()
            if not s.startswith("|"):
                return False
            # A sequence like | :--- | ---: | :--: |
            # Accepts variable spaces around segments.
            parts = [p.strip() for p in s.split("|")]
            # Leading/trailing splits produce empty parts; require at least 3 non-empty (| seg |)
            segs = [p for p in parts if p]
            if len(segs) < 2:
                return False
            for seg in segs:
                # allow combinations of colons and 3+ dashes with optional spaces
                core = seg.replace(" ", "")
                if not core:
                    return False
                # must be something like :---, ---:, :---:, or ---
                # ensure at least 3 dashes exist regardless of colons at ends
                dashes = core.strip(":")
                # Be permissive: accept 1 or more dashes to accommodate loose authoring
                if len(dashes) < 1 or any(ch != '-' for ch in dashes):
                    return False
            return True

        def is_table_row(line: str) -> bool:
            # Data rows commonly start with '|' and may or may not end with '|'. Be permissive.
            return line.lstrip().startswith("|")

        n = len(lines)
        i = 0
        while i < n:
            line = lines[i]
            if not is_table_header(line):
                i += 1
                continue
            # find next non-empty line for alignment
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j >= n or not is_alignment(lines[j]):
                # Not a proper table header; continue scanning after current line
                i += 1
                continue
            # Collect header, alignment, then contiguous data rows
            block: list[str] = [lines[i].rstrip("\r\n"), lines[j].rstrip("\r\n")]
            k = j + 1
            while k < n and lines[k].strip() and is_table_row(lines[k]):
                block.append(lines[k].rstrip("\r\n"))
                k += 1
            if len(block) >= 2:
                return "\n".join(block)
            i = k
        return None

    
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
