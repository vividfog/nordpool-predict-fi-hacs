from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from aiohttp import ClientError
from homeassistant.helpers.update_coordinator import UpdateFailed
from zoneinfo import ZoneInfo

from custom_components.nordpool_predict_fi.const import (
    CUSTOM_WINDOW_KEY,
    DEFAULT_CUSTOM_WINDOW_END_HOUR,
    DEFAULT_CUSTOM_WINDOW_HOURS,
    DEFAULT_CUSTOM_WINDOW_START_HOUR,
)
from custom_components.nordpool_predict_fi.coordinator import (
    NordpoolPredictCoordinator,
    PriceWindow,
    SeriesPoint,
)


class _MockResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    async def __aenter__(self) -> "_MockResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise AssertionError(f"unexpected status {self.status}")

    async def json(self, *args, **kwargs) -> Any:
        return self._payload

    async def text(self) -> str:
        if isinstance(self._payload, str):
            return self._payload
        raise AssertionError("Unexpected text() call for non-string payload")


class _MockSession:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self._payloads = payloads

    def get(self, url: str) -> _MockResponse:
        if url in self._payloads:
            return _MockResponse(self._payloads[url])
        if url.startswith("https://sahkotin.fi/prices.csv"):
            payload = self._payloads.get("sahkotin")
            if payload is None:
                raise AssertionError("Sähkötin payload missing")
            return _MockResponse(payload)
        raise AssertionError(f"Unexpected URL requested: {url}")


@pytest.mark.asyncio
async def test_coordinator_parses_series(hass, enable_custom_integrations, monkeypatch) -> None:
    base_url = "https://example.com/deploy"
    helsinki = ZoneInfo("Europe/Helsinki")
    now_helsinki = datetime(2024, 1, 1, 13, 0, tzinfo=helsinki)
    now = now_helsinki.astimezone(timezone.utc)
    forecast_start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    forecast = [
        [(forecast_start + timedelta(hours=offset)).timestamp() * 1000, float(offset)]
        for offset in range(72)
    ]
    wind = [
        [(forecast_start + timedelta(hours=offset)).timestamp() * 1000, 3200.0 + offset * 5]
        for offset in range(120)
    ]
    narration_fi = "  *Lyhyt tiivistelmä ensimmäiselle riville.*  \nLisärivi."
    narration_en = "Short summary on the first line.\nMore detail."
    realized_csv = "timestamp,price\n" + "\n".join(
        f"{(forecast_start + timedelta(hours=offset)).isoformat()},{5.0 + offset}"
        for offset in range(13)
    )

    session = _MockSession(
        {
            f"{base_url}/prediction.json": forecast,
            f"{base_url}/windpower.json": wind,
            f"{base_url}/narration.md": narration_fi,
            f"{base_url}/narration_en.md": narration_en,
            "sahkotin": realized_csv,
        }
    )

    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.async_get_clientsession",
        lambda hass: session,
    )

    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url=base_url,
        update_interval=timedelta(minutes=15),
    )
    monkeypatch.setattr(coordinator, "_current_time", lambda: now)

    data = await coordinator._async_update_data()
    coordinator.async_set_updated_data(data)

    data = coordinator.data
    price_section = data["price"]
    # Current point is now found from merged series (realized + forecast)
    # At 11:00 UTC (now), the realized price is 5.0 + 11 = 16.0
    assert price_section["current"].value == pytest.approx(16.0)
    assert price_section["forecast_start"] == datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)
    assert price_section["forecast"][0].datetime == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert price_section["forecast"][0].value == pytest.approx(5.0)
    assert price_section["forecast"][12].value == pytest.approx(17.0)
    assert price_section["forecast"][13].value == pytest.approx(13.0)
    assert len(price_section["forecast"]) == 72
    # Cheapest windows may include the current hour but not start more than duration-1 hours ago
    current_hour_anchor = now.replace(minute=0, second=0, microsecond=0)
    windows = price_section["cheapest_windows"]
    windows_meta = price_section["cheapest_windows_meta"]
    assert windows_meta["lookahead_hours"] == coordinator.cheapest_window_lookahead_hours
    assert windows_meta["lookahead_limit"] == coordinator._cheapest_window_lookahead_limit(now)
    window_3h = windows[3]
    assert isinstance(window_3h, PriceWindow)
    assert window_3h.start == datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)
    assert window_3h.start >= current_hour_anchor - timedelta(hours=2)
    assert window_3h.end == datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)
    assert window_3h.average == pytest.approx(14.0)
    assert window_3h.end > now
    assert len(window_3h.points) == 3
    window_6h = windows[6]
    assert isinstance(window_6h, PriceWindow)
    assert window_6h.start == datetime(2024, 1, 1, 6, 0, tzinfo=timezone.utc)
    assert window_6h.start >= current_hour_anchor - timedelta(hours=5)
    assert window_6h.end == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert window_6h.average == pytest.approx(13.5)
    assert window_6h.end > now
    window_12h = windows[12]
    assert isinstance(window_12h, PriceWindow)
    assert window_12h.start == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert window_12h.start >= current_hour_anchor - timedelta(hours=11)
    assert window_12h.end == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert window_12h.average == pytest.approx(10.5)
    assert window_12h.end > now
    custom_section = price_section[CUSTOM_WINDOW_KEY]
    assert custom_section["hours"] == DEFAULT_CUSTOM_WINDOW_HOURS
    assert custom_section["start_hour"] == DEFAULT_CUSTOM_WINDOW_START_HOUR
    assert custom_section["end_hour"] == DEFAULT_CUSTOM_WINDOW_END_HOUR
    assert custom_section["lookahead_hours"] == coordinator.custom_window_lookahead_hours
    assert custom_section["lookahead_limit"] == coordinator._custom_window_lookahead_limit(now)
    custom_window = custom_section["window"]
    assert isinstance(custom_window, PriceWindow)
    assert custom_window.duration_hours == DEFAULT_CUSTOM_WINDOW_HOURS
    assert len(custom_window.points) == DEFAULT_CUSTOM_WINDOW_HOURS
    daily_averages = price_section["daily_averages"]
    assert len(daily_averages) == 2
    first_day = daily_averages[0]
    assert first_day.date == datetime(2024, 1, 2, tzinfo=helsinki).date()
    assert first_day.start == datetime(2024, 1, 2, 0, 0, tzinfo=helsinki)
    assert first_day.end == datetime(2024, 1, 3, 0, 0, tzinfo=helsinki)
    assert len(first_day.points) == 24
    assert first_day.points[0].datetime == datetime(2024, 1, 1, 22, 0, tzinfo=timezone.utc)
    assert first_day.points[-1].datetime == datetime(2024, 1, 2, 21, 0, tzinfo=timezone.utc)
    assert first_day.points[0].value == pytest.approx(22.0)
    assert first_day.points[-1].value == pytest.approx(45.0)
    expected_first_average = sum(point.value for point in first_day.points) / len(first_day.points)
    assert first_day.average == pytest.approx(expected_first_average)
    second_day = daily_averages[1]
    assert second_day.date == datetime(2024, 1, 3, tzinfo=helsinki).date()
    assert second_day.start == datetime(2024, 1, 3, 0, 0, tzinfo=helsinki)
    assert second_day.end == datetime(2024, 1, 4, 0, 0, tzinfo=helsinki)
    assert len(second_day.points) == 24
    assert second_day.points[0].datetime == datetime(2024, 1, 2, 22, 0, tzinfo=timezone.utc)
    assert second_day.points[-1].datetime == datetime(2024, 1, 3, 21, 0, tzinfo=timezone.utc)
    assert second_day.points[0].value == pytest.approx(46.0)
    assert second_day.points[-1].value == pytest.approx(69.0)
    expected_second_average = sum(point.value for point in second_day.points) / len(second_day.points)
    assert second_day.average == pytest.approx(expected_second_average)

    wind_section = data["windpower"]
    # Wind data now starts from today midnight Helsinki (2023-12-31 22:00 UTC -> first available at 00:00 UTC)
    assert wind_section["series"][0].datetime == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    hours_since_start = int((now - forecast_start).total_seconds() // 3600)
    expected_wind_value = 3200.0 + hours_since_start * 5
    assert wind_section["current"].value == pytest.approx(expected_wind_value)
    assert len(wind_section["series"]) == 120
    narration = data["narration"]
    assert narration["fi"]["content"] == "*Lyhyt tiivistelmä ensimmäiselle riville.*  \nLisärivi."
    assert narration["fi"]["summary"] == "Lyhyt tiivistelmä ensimmäiselle riville."
    assert narration["fi"]["source"] == f"{base_url}/narration.md"
    assert narration["en"]["summary"] == "Short summary on the first line."


@pytest.mark.asyncio
async def test_coordinator_merges_realized_and_forecast(
    hass, enable_custom_integrations, monkeypatch
) -> None:
    base_url = "https://example.com/deploy"
    helsinki = ZoneInfo("Europe/Helsinki")
    now_helsinki = datetime(2024, 1, 1, 15, 0, tzinfo=helsinki)
    now = now_helsinki.astimezone(timezone.utc)
    forecast_start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    forecast = [
        [(forecast_start + timedelta(hours=offset)).timestamp() * 1000, float(offset)]
        for offset in range(96)
    ]
    realized_csv = "timestamp,price\n" + "\n".join(
        f"{(forecast_start + timedelta(hours=offset)).isoformat()},{10.0 + offset}"
        for offset in range(5)
    )

    session = _MockSession(
        {
            f"{base_url}/prediction.json": forecast,
            f"{base_url}/windpower.json": [],
            f"{base_url}/narration.md": "Example",
            f"{base_url}/narration_en.md": "Example EN",
            "sahkotin": realized_csv,
        }
    )

    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.async_get_clientsession",
        lambda hass: session,
    )

    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url=base_url,
        update_interval=timedelta(minutes=15),
    )
    monkeypatch.setattr(coordinator, "_current_time", lambda: now)

    data = await coordinator._async_update_data()

    price_section = data["price"]
    # Merged series starts from today midnight and uses realized data
    assert price_section["forecast"][0].datetime == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert price_section["forecast"][0].value == pytest.approx(10.0)  # Realized price
    assert price_section["forecast"][4].datetime == datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc)
    assert price_section["forecast"][4].value == pytest.approx(14.0)  # Last realized
    assert price_section["forecast"][5].datetime == datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc)
    assert price_section["forecast"][5].value == pytest.approx(5.0)  # Forecast starts
    assert price_section["forecast_start"] == datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc)
    assert price_section["forecast"][-1].datetime == datetime(2024, 1, 4, 23, 0, tzinfo=timezone.utc)
    # Current point is at or before now (15:00 Helsinki = 13:00 UTC) from merged series
    # At 13:00 UTC, the forecast value is 13.0
    assert price_section["current"].value == pytest.approx(13.0)


@pytest.mark.asyncio
async def test_coordinator_current_none_when_no_past_points(
    hass, enable_custom_integrations, monkeypatch
) -> None:
    base_url = "https://example.com/deploy"
    helsinki = ZoneInfo("Europe/Helsinki")
    now_helsinki = datetime(2024, 1, 1, 10, 0, tzinfo=helsinki)
    now = now_helsinki.astimezone(timezone.utc)
    future_start = now + timedelta(hours=1)
    forecast = [
        [(future_start + timedelta(hours=offset)).timestamp() * 1000, float(offset + 1)]
        for offset in range(12)
    ]
    wind = [
        [(future_start + timedelta(hours=offset)).timestamp() * 1000, 4000.0 + offset * 20]
        for offset in range(6)
    ]

    realized_csv = "timestamp,price\n"

    session = _MockSession(
        {
            f"{base_url}/prediction.json": forecast,
            f"{base_url}/windpower.json": wind,
            f"{base_url}/narration.md": "Example FI",
            f"{base_url}/narration_en.md": "Example EN",
            "sahkotin": realized_csv,
        }
    )

    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.async_get_clientsession",
        lambda hass: session,
    )

    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url=base_url,
        update_interval=timedelta(minutes=15),
    )
    monkeypatch.setattr(coordinator, "_current_time", lambda: now)

    data = await coordinator._async_update_data()
    price_section = data["price"]
    assert price_section["current"] is None
    assert price_section["forecast"][0].datetime == future_start
    assert price_section["forecast_start"] == future_start
    wind_section = data["windpower"]
    assert wind_section is not None
    assert wind_section["current"] is None
    assert wind_section["series"][0].datetime == future_start

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raised_exception",
    (
        FileNotFoundError("missing"),
        UpdateFailed("boom"),
        ClientError("network"),
        ValueError("bad json"),
        asyncio.TimeoutError(),
    ),
    ids=["file_not_found", "update_failed", "client_error", "value_error", "timeout"],
)
async def test_safe_fetch_artifact_swallows_errors(
    hass, enable_custom_integrations, monkeypatch, raised_exception
) -> None:
    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url="https://example.com/deploy",
        update_interval=timedelta(minutes=15),
    )

    async def _failing_fetch(session, suffix):
        raise raised_exception

    monkeypatch.setattr(coordinator, "_fetch_json", _failing_fetch)

    result = await coordinator._safe_fetch_artifact(None, "windpower.json")
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raised_exception",
    (
        FileNotFoundError("missing"),
        UpdateFailed("boom"),
        ClientError("network"),
        asyncio.TimeoutError(),
    ),
    ids=["file_not_found", "update_failed", "client_error", "timeout"],
)
async def test_safe_fetch_artifact_text_swallows_errors(
    hass, enable_custom_integrations, monkeypatch, raised_exception
) -> None:
    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url="https://example.com/deploy",
        update_interval=timedelta(minutes=15),
    )

    async def _failing_fetch(session, suffix):
        raise raised_exception

    monkeypatch.setattr(coordinator, "_fetch_text", _failing_fetch)

    result = await coordinator._safe_fetch_artifact_text(None, "narration.md")
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raised_exception",
    (
        UpdateFailed("boom"),
        ClientError("network"),
        asyncio.TimeoutError(),
    ),
    ids=["update_failed", "client_error", "timeout"],
)
async def test_safe_fetch_sahkotin_series_swallows_errors(
    hass, enable_custom_integrations, monkeypatch, raised_exception
) -> None:
    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url="https://example.com/deploy",
        update_interval=timedelta(minutes=15),
    )

    async def _failing_fetch(session, start, end):
        raise raised_exception

    monkeypatch.setattr(coordinator, "_fetch_sahkotin_csv", _failing_fetch)

    result = await coordinator._safe_fetch_sahkotin_series(
        None,
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    assert result == []


@pytest.mark.asyncio
async def test_fetch_json_invalid_payload_raises_update_failed(
    hass, enable_custom_integrations
) -> None:
    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url="https://example.com/deploy",
        update_interval=timedelta(minutes=15),
    )

    class _InvalidJsonSession:
        def get(self, url: str):
            class _InvalidResponse:
                def __init__(self) -> None:
                    self.status = 200

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return None

                def raise_for_status(self):
                    return None

                async def json(self, *args, **kwargs):
                    raise ValueError("broken")

            return _InvalidResponse()

    session = _InvalidJsonSession()

    with pytest.raises(UpdateFailed):
        await coordinator._fetch_json(session, "prediction.json")


@pytest.mark.asyncio
async def test_custom_window_respects_hour_mask(hass, enable_custom_integrations) -> None:
    coordinator = _coordinator(hass)
    base = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    series = [
        SeriesPoint(datetime=base + timedelta(hours=offset), value=float(10 + offset))
        for offset in range(24)
    ]
    now = base + timedelta(hours=10)
    helsinki_tz = coordinator._get_helsinki_timezone()
    custom_entry = coordinator._build_custom_window_entry(series, now, helsinki_tz)
    assert custom_entry["lookahead_hours"] == coordinator.custom_window_lookahead_hours
    assert custom_entry["lookahead_limit"] == coordinator._custom_window_lookahead_limit(now)
    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": series,
                "current": series[10],
                "cheapest_windows": {},
                CUSTOM_WINDOW_KEY: custom_entry,
                "now": now,
                "forecast_start": series[0].datetime,
                "daily_averages": [],
            },
            "windpower": None,
            "narration": {},
        }
    )

    initial = coordinator.data["price"][CUSTOM_WINDOW_KEY]
    assert isinstance(initial["window"], PriceWindow)
    assert initial["window"].duration_hours == DEFAULT_CUSTOM_WINDOW_HOURS
    assert initial["lookahead_hours"] == coordinator.custom_window_lookahead_hours
    assert initial["lookahead_limit"] == coordinator._custom_window_lookahead_limit(now)

    coordinator.set_custom_window_start_hour(12)
    coordinator.set_custom_window_end_hour(14)
    narrowed = coordinator.data["price"][CUSTOM_WINDOW_KEY]
    assert narrowed["window"] is None
    assert narrowed["hours"] == DEFAULT_CUSTOM_WINDOW_HOURS
    assert narrowed["lookahead_hours"] == coordinator.custom_window_lookahead_hours
    assert narrowed["lookahead_limit"] == coordinator._custom_window_lookahead_limit(now)

    coordinator.set_custom_window_hours(2)
    updated = coordinator.data["price"][CUSTOM_WINDOW_KEY]
    assert updated["hours"] == 2
    assert isinstance(updated["window"], PriceWindow)
    assert updated["window"].duration_hours == 2
    assert updated["lookahead_hours"] == coordinator.custom_window_lookahead_hours
    assert updated["lookahead_limit"] == coordinator._custom_window_lookahead_limit(now)
    for point in updated["window"].points:
        local_hour = point.datetime.astimezone(helsinki_tz).hour
        assert 12 <= local_hour <= 14


@pytest.mark.asyncio
async def test_custom_window_respects_lookahead_limit(hass, enable_custom_integrations) -> None:
    coordinator = _coordinator(hass)
    base = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    series: list[SeriesPoint] = []
    for offset in range(48):
        if offset < 12:
            value = 50.0
        elif offset < 20:
            value = 80.0
        else:
            value = 5.0
        series.append(SeriesPoint(datetime=base + timedelta(hours=offset), value=value))

    now = base
    helsinki_tz = coordinator._get_helsinki_timezone()
    coordinator.set_custom_window_hours(4)
    coordinator.set_custom_window_lookahead_hours(12)

    limited_entry = coordinator._build_custom_window_entry(series, now, helsinki_tz)
    limited_window = limited_entry["window"]
    assert isinstance(limited_window, PriceWindow)
    assert limited_window.start == base
    assert limited_window.end == base + timedelta(hours=4)

    coordinator.set_custom_window_lookahead_hours(48)
    expanded_entry = coordinator._build_custom_window_entry(series, now, helsinki_tz)
    expanded_window = expanded_entry["window"]
    assert isinstance(expanded_window, PriceWindow)
    assert expanded_window.start == base + timedelta(hours=20)
    assert expanded_window.end == base + timedelta(hours=24)


def test_cheapest_windows_respect_shared_lookahead(hass, enable_custom_integrations, monkeypatch) -> None:
    coordinator = _coordinator(hass)
    base = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    now = base
    monkeypatch.setattr(coordinator, "_current_time", lambda: now)
    series = [
        SeriesPoint(datetime=base + timedelta(hours=offset), value=float(offset))
        for offset in range(200)
    ]

    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": series,
                "current": series[0],
                "cheapest_windows": {},
                "cheapest_windows_meta": {},
                CUSTOM_WINDOW_KEY: coordinator._empty_custom_window_entry(),
                "now": now,
                "forecast_start": series[0].datetime,
                "daily_averages": [],
            },
            "windpower": None,
            "narration": {},
        }
    )
    coordinator._rebuild_cheapest_windows_from_cached_data()

    meta = coordinator.data["price"]["cheapest_windows_meta"]
    limit_default = coordinator._cheapest_window_lookahead_limit(now)
    assert meta["lookahead_hours"] == coordinator.cheapest_window_lookahead_hours == 168
    assert meta["lookahead_limit"] == limit_default

    updates = 0

    def _capture_update() -> None:
        nonlocal updates
        updates += 1

    monkeypatch.setattr(coordinator, "async_update_listeners", _capture_update)

    coordinator.set_cheapest_window_lookahead_hours(100)
    assert coordinator.cheapest_window_lookahead_hours == 100
    assert updates == 1
    limit_100 = coordinator._cheapest_window_lookahead_limit(now)
    meta_mid = coordinator.data["price"]["cheapest_windows_meta"]
    assert meta_mid["lookahead_hours"] == 100
    assert meta_mid["lookahead_limit"] == limit_100

    coordinator.set_cheapest_window_lookahead_hours(200)
    assert coordinator.cheapest_window_lookahead_hours == 168
    assert updates == 2
    expected_limit = coordinator._cheapest_window_lookahead_limit(now)
    meta_post = coordinator.data["price"]["cheapest_windows_meta"]
    assert meta_post["lookahead_hours"] == 168
    assert meta_post["lookahead_limit"] == expected_limit
    rebuilt_windows = coordinator.data["price"]["cheapest_windows"]
    for window in rebuilt_windows.values():
        if window is None:
            continue
        assert window.end <= expected_limit

    coordinator.set_cheapest_window_lookahead_hours(0)
    assert coordinator.cheapest_window_lookahead_hours == 1
    assert updates == 3
    meta_min = coordinator.data["price"]["cheapest_windows_meta"]
    assert meta_min["lookahead_hours"] == 1
    min_limit = coordinator._cheapest_window_lookahead_limit(now)
    assert meta_min["lookahead_limit"] == min_limit


def _coordinator(hass) -> NordpoolPredictCoordinator:
    return NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url="https://example.com/deploy",
        update_interval=timedelta(minutes=15),
    )


def test_find_cheapest_window_requires_hourly_sequence(hass, enable_custom_integrations) -> None:
    coordinator = _coordinator(hass)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    irregular_series = [
        SeriesPoint(datetime=base, value=10.0),
        SeriesPoint(datetime=base + timedelta(hours=1), value=11.0),
        SeriesPoint(datetime=base + timedelta(hours=2, minutes=30), value=9.0),
    ]

    assert coordinator._find_cheapest_window(irregular_series, 3) is None


def test_parse_sahkotin_csv_filters_and_normalizes(hass, enable_custom_integrations) -> None:
    coordinator = _coordinator(hass)
    earliest = datetime(2024, 1, 1, 10, tzinfo=timezone.utc)
    csv_text = "\n".join(
        [
            "timestamp,price",
            "2024-01-01T09:00:00Z,18.2",
            "2024-01-01 12:00:00,19.4",
            "invalid,line",
            "2024-01-01T13:00:00+02:00,20.1",
            ",",
            "2024-01-01T14:00:00,not-a-number",
        ]
    )

    series = coordinator._parse_sahkotin_csv(csv_text, earliest)

    assert len(series) == 2
    assert series[0].datetime == datetime(2024, 1, 1, 11, tzinfo=timezone.utc)
    assert series[0].value == pytest.approx(20.1)
    assert series[1].datetime == datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    assert series[1].value == pytest.approx(19.4)


def test_build_summary_skips_markdown_grid_and_truncates(hass, enable_custom_integrations) -> None:
    coordinator = _coordinator(hass)
    content = (
        "| heading | row |\n"
        "\n"
        "  __This line will be very long " + "x" * 260 + "__\n"
        "\n"
        "  Short fallback line.\n"
    )

    summary = coordinator._build_summary(content)

    assert summary.endswith("...")
    assert len(summary) <= 255
    # Summary should not include the grid header or pipes
    assert "|" not in summary


def test_narration_section_no_markdown_grid_key(hass, enable_custom_integrations) -> None:
    coordinator = _coordinator(hass)
    content = (
        "Intro paragraph.\n\n"
        "| H | A |\n"
        "|:--|:-:|\n"
        "| r1 | c1 |\n"
        "| r2 | c2 |\n"
        "\nTail paragraph.\n"
    )

    section = coordinator._build_narration_section("narration_en.md", content)
    assert section is not None
    # Section contains only the expected keys
    assert set(section.keys()) == {"content", "summary", "source"}
