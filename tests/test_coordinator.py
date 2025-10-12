from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from aiohttp import ClientError
from homeassistant.helpers.update_coordinator import UpdateFailed
from zoneinfo import ZoneInfo

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
        include_windpower=True,
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
    assert price_section["forecast"][0].datetime == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert price_section["forecast"][0].value == pytest.approx(5.0)
    assert price_section["forecast"][12].value == pytest.approx(17.0)
    assert price_section["forecast"][13].value == pytest.approx(13.0)
    assert len(price_section["forecast"]) == 72
    # Cheapest windows now use merged series, so they start from realized data
    windows = price_section["cheapest_windows"]
    window_3h = windows[3]
    assert isinstance(window_3h, PriceWindow)
    assert window_3h.start == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert window_3h.end == datetime(2024, 1, 1, 3, 0, tzinfo=timezone.utc)
    assert window_3h.average == pytest.approx(6.0)
    assert len(window_3h.points) == 3
    window_6h = windows[6]
    assert isinstance(window_6h, PriceWindow)
    assert window_6h.average == pytest.approx(7.5)
    assert window_6h.end - window_6h.start == timedelta(hours=6)
    window_12h = windows[12]
    assert isinstance(window_12h, PriceWindow)
    assert window_12h.average == pytest.approx(10.5)

    wind_section = data["windpower"]
    # Wind data now starts from today midnight Helsinki (2023-12-31 22:00 UTC -> first available at 00:00 UTC)
    assert wind_section["series"][0].datetime == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert wind_section["current"].value == pytest.approx(3200.0)
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
        include_windpower=False,
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
    assert price_section["forecast"][-1].datetime == datetime(2024, 1, 4, 23, 0, tzinfo=timezone.utc)
    # Current point is at or before now (15:00 Helsinki = 13:00 UTC) from merged series
    # At 13:00 UTC, the forecast value is 13.0
    assert price_section["current"].value == pytest.approx(13.0)

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
async def test_safe_fetch_optional_swallows_errors(
    hass, enable_custom_integrations, monkeypatch, raised_exception
) -> None:
    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url="https://example.com/deploy",
        include_windpower=True,
        update_interval=timedelta(minutes=15),
    )

    async def _failing_fetch(session, suffix):
        raise raised_exception

    monkeypatch.setattr(coordinator, "_fetch_json", _failing_fetch)

    result = await coordinator._safe_fetch_optional(None, "windpower.json")
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
async def test_safe_fetch_optional_text_swallows_errors(
    hass, enable_custom_integrations, monkeypatch, raised_exception
) -> None:
    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url="https://example.com/deploy",
        include_windpower=True,
        update_interval=timedelta(minutes=15),
    )

    async def _failing_fetch(session, suffix):
        raise raised_exception

    monkeypatch.setattr(coordinator, "_fetch_text", _failing_fetch)

    result = await coordinator._safe_fetch_optional_text(None, "narration.md")
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
        include_windpower=True,
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
        include_windpower=True,
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


def _coordinator(hass, include_windpower: bool = True) -> NordpoolPredictCoordinator:
    return NordpoolPredictCoordinator(
        hass=hass,
        entry_id="test",
        base_url="https://example.com/deploy",
        include_windpower=include_windpower,
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


def test_build_summary_skips_tables_and_truncates(hass, enable_custom_integrations) -> None:
    coordinator = _coordinator(hass)
    content = (
        "| table | row |\n"
        "\n"
        "  __This line will be very long " + "x" * 260 + "__\n"
        "\n"
        "  Short fallback line.\n"
    )

    summary = coordinator._build_summary(content)

    assert summary.endswith("...")
    assert len(summary) <= 255
    assert "table" not in summary
