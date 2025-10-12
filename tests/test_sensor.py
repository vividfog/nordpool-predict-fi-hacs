from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nordpool_predict_fi import sensor
from custom_components.nordpool_predict_fi.const import (
    ATTR_FORECAST,
    ATTR_NEXT_VALID_FROM,
    ATTR_RAW_SOURCE,
    ATTR_WIND_FORECAST,
    DATA_COORDINATOR,
    DOMAIN,
)
from custom_components.nordpool_predict_fi.coordinator import (
    NordpoolPredictCoordinator,
    SeriesPoint,
)


def _series_point(hours: int, value: float, base: datetime) -> SeriesPoint:
    target = base + timedelta(hours=hours)
    return SeriesPoint(datetime=target, value=value)


@pytest.mark.asyncio
async def test_async_setup_entry_registers_entities(hass, enable_custom_integrations) -> None:
    """Price sensor should register alongside optional wind sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Nordpool Predict FI",
        data={},
    )
    entry.add_to_hass(hass)

    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id=entry.entry_id,
        base_url="https://example.com/deploy",
        include_windpower=True,
        update_interval=timedelta(minutes=15),
    )

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    forecast_series = [
        _series_point(1, 12.3, now),
        _series_point(2, 8.1, now),
        _series_point(3, 20.5, now),
    ]

    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": forecast_series,
                "current": forecast_series[0],
            },
            "windpower": {
                "series": [
                    _series_point(1, 3500.0, now),
                    _series_point(2, 4100.0, now),
                ],
                "current": _series_point(1, 3500.0, now),
            },
        }
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {DATA_COORDINATOR: coordinator}

    added: list[sensor.NordpoolBaseSensor] = []

    def _add_entities(new_entities: list[Any], update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)

    assert {type(entity) for entity in added} == {
        sensor.NordpoolPriceSensor,
        sensor.NordpoolWindpowerSensor,
    }

    price = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor))
    attrs = price.extra_state_attributes
    assert price.native_value == pytest.approx(12.3)
    assert attrs[ATTR_FORECAST][0]["value"] == pytest.approx(12.3)
    assert attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert attrs[ATTR_NEXT_VALID_FROM] == forecast_series[0].datetime.isoformat()

    wind = next(entity for entity in added if isinstance(entity, sensor.NordpoolWindpowerSensor))
    wind_attrs = wind.extra_state_attributes
    assert wind.native_value == pytest.approx(3500.0)
    assert len(wind_attrs[ATTR_WIND_FORECAST]) == 2
    assert wind_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert wind_attrs[ATTR_NEXT_VALID_FROM] == forecast_series[0].datetime.isoformat()


@pytest.mark.asyncio
async def test_async_setup_entry_without_optional_feeds(hass, enable_custom_integrations) -> None:
    """Only price sensor should be added when wind is disabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Nordpool Predict FI",
        data={},
    )
    entry.add_to_hass(hass)

    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id=entry.entry_id,
        base_url="https://example.com/deploy",
        include_windpower=False,
        update_interval=timedelta(minutes=15),
    )

    now = datetime.now(timezone.utc)
    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": [
                    _series_point(1, 5.0, now),
                ],
                "current": _series_point(1, 5.0, now),
            },
            "windpower": None,
        }
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {DATA_COORDINATOR: coordinator}

    added: list[sensor.NordpoolBaseSensor] = []

    def _add_entities(new_entities: list[Any], update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)

    assert len(added) == 1
    assert isinstance(added[0], sensor.NordpoolPriceSensor)
    attrs = added[0].extra_state_attributes
    assert attrs[ATTR_NEXT_VALID_FROM] == _series_point(1, 5.0, now).datetime.isoformat()
