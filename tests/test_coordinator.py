from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from aiohttp import ClientError
from homeassistant.helpers.update_coordinator import UpdateFailed
from zoneinfo import ZoneInfo

from custom_components.nordpool_predict_fi.coordinator import NordpoolPredictCoordinator


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


class _MockSession:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self._payloads = payloads

    def get(self, url: str) -> _MockResponse:
        if url not in self._payloads:
            raise AssertionError(f"Unexpected URL requested: {url}")
        return _MockResponse(self._payloads[url])


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

    session = _MockSession(
        {
            f"{base_url}/prediction.json": forecast,
            f"{base_url}/windpower.json": wind,
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
    assert price_section["current"].value == pytest.approx(23.0)
    assert price_section["forecast"][0].datetime == datetime(2024, 1, 1, 23, 0, tzinfo=timezone.utc)
    assert len(price_section["forecast"]) == 49

    wind_section = data["windpower"]
    assert wind_section["series"][0].datetime == datetime(2024, 1, 1, 23, 0, tzinfo=timezone.utc)
    assert wind_section["current"].value == pytest.approx(3200.0 + 23 * 5)
    assert len(wind_section["series"]) == 97


@pytest.mark.asyncio
async def test_coordinator_filters_day_after_tomorrow_after_release(
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

    session = _MockSession(
        {
            f"{base_url}/prediction.json": forecast,
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
    expected_start = datetime(2024, 1, 2, 23, 0, tzinfo=timezone.utc)
    assert price_section["forecast"][0].datetime == expected_start
    assert price_section["current"].value == pytest.approx(47.0)

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
