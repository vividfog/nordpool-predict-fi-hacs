from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nordpool_predict_fi import sensor
from custom_components.nordpool_predict_fi.const import (
    ATTR_FORECAST,
    ATTR_FORECAST_START,
    ATTR_LANGUAGE,
    ATTR_NARRATION_CONTENT,
    ATTR_NARRATION_SUMMARY,
    ATTR_NEXT_VALID_FROM,
    ATTR_RAW_SOURCE,
    ATTR_SOURCE_URL,
    ATTR_TIMESTAMP,
    ATTR_WIND_FORECAST,
    ATTR_WINDOW_DURATION,
    ATTR_WINDOW_END,
    ATTR_WINDOW_POINTS,
    ATTR_WINDOW_START,
    CHEAPEST_WINDOW_HOURS,
    DATA_COORDINATOR,
    DOMAIN,
    NARRATION_LANGUAGES,
    NEXT_HOURS,
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
    """Price and wind sensors should register together."""
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
        update_interval=timedelta(minutes=15),
    )

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    values = [12.3, 9.5, 8.0, 8.5, 7.0, 7.1, 9.2, 10.5, 11.0, 12.5, 13.0, 14.0, 15.0]
    current_point = _series_point(0, values[0], now)
    future_values = values[1:]
    forecast_series = [
        _series_point(index + 1, value, now) for index, value in enumerate(future_values)
    ]
    merged_price_series = [current_point, *forecast_series]
    forecast_start = forecast_series[0].datetime
    next_window_anchor = now + timedelta(hours=1)
    cheapest_windows = {
        hours: coordinator._find_cheapest_window(
            merged_price_series,
            hours,
            earliest_start=next_window_anchor,
        )
        for hours in CHEAPEST_WINDOW_HOURS
    }
    narration_section = {
        "fi": {
            "summary": "Tämä on esimerkkitiivistelmä.",
            "content": "Tämä on esimerkkitiivistelmä.\nLisätietoja löytyy verkkosivulta.",
            "source": "https://example.com/deploy/narration.md",
        },
        "en": {
            "summary": "This is a sample summary.",
            "content": "This is a sample summary.\nMore details on the website.",
            "source": "https://example.com/deploy/narration_en.md",
        },
    }

    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": merged_price_series,
                "current": current_point,
                "cheapest_windows": cheapest_windows,
                "forecast_start": forecast_start,
            },
            "windpower": {
                "series": [
                    _series_point(0, 3500.0, now),
                    _series_point(1, 4100.0, now),
                    _series_point(2, 4200.0, now),
                ],
                "current": _series_point(0, 3500.0, now),
            },
            "narration": narration_section,
        }
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {DATA_COORDINATOR: coordinator}

    added: list[sensor.NordpoolBaseSensor] = []

    def _add_entities(new_entities: list[Any], update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)

    expected_entity_count = (
        6  # NordpoolPriceSensor, NordpoolPriceNowSensor, and 4 next hour sensors
        + 2  # NordpoolWindpowerSensor and NordpoolWindpowerNowSensor
        + len(CHEAPEST_WINDOW_HOURS)  # Cheapest window sensors
        + len(NARRATION_LANGUAGES)  # Narration sensors
    )
    assert len(added) == expected_entity_count
    assert sum(isinstance(entity, sensor.NordpoolPriceSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolPriceNowSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolWindpowerSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolWindpowerNowSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolNarrationSensor) for entity in added) == len(NARRATION_LANGUAGES)
    # Assert only expected entity classes are present
    allowed_types = (
        sensor.NordpoolPriceSensor,
        sensor.NordpoolPriceNowSensor,
        sensor.NordpoolPriceNextHoursSensor,
        sensor.NordpoolWindpowerSensor,
        sensor.NordpoolWindpowerNowSensor,
        sensor.NordpoolCheapestWindowSensor,
        sensor.NordpoolNarrationSensor,
    )
    assert all(isinstance(entity, allowed_types) for entity in added)
    price = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor))
    attrs = price.extra_state_attributes
    assert price.native_value == pytest.approx(round(current_point.value, 1))
    assert attrs[ATTR_FORECAST][0]["value"] == pytest.approx(round(current_point.value, 1))
    assert attrs[ATTR_FORECAST_START] == forecast_start.isoformat()
    assert attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert ATTR_NEXT_VALID_FROM not in attrs

    price_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceNowSensor))
    price_now_attrs = price_now.extra_state_attributes
    assert price_now.native_value == pytest.approx(round(current_point.value, 1))
    assert price_now_attrs[ATTR_TIMESTAMP] == current_point.datetime.isoformat()
    assert price_now_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"

    next_price_entities = [
        entity for entity in added if isinstance(entity, sensor.NordpoolPriceNextHoursSensor)
    ]
    assert len(next_price_entities) == len(NEXT_HOURS)
    next_by_hours: dict[int, sensor.NordpoolPriceNextHoursSensor] = {}
    for entity in next_price_entities:
        for hours in NEXT_HOURS:
            if entity.unique_id.endswith(f"_price_next_{hours}h"):
                next_by_hours[hours] = entity
                break
    assert set(next_by_hours) == set(NEXT_HOURS)
    for hours, entity in next_by_hours.items():
        attrs_next = entity.extra_state_attributes
        timestamp_raw = attrs_next[ATTR_TIMESTAMP]
        if len(future_values) >= hours:
            expected_average = round(sum(future_values[:hours]) / hours, 1)
            assert entity.native_value == pytest.approx(expected_average)
            assert timestamp_raw is not None
            assert datetime.fromisoformat(timestamp_raw) > now
        else:
            assert entity.native_value is None
            assert timestamp_raw is None
        assert attrs_next[ATTR_RAW_SOURCE] == "https://example.com/deploy"

    wind = next(entity for entity in added if isinstance(entity, sensor.NordpoolWindpowerSensor))
    wind_attrs = wind.extra_state_attributes
    assert wind.native_value == 3500
    assert len(wind_attrs[ATTR_WIND_FORECAST]) == 3
    first_wind_forecast = wind_attrs[ATTR_WIND_FORECAST][0]
    assert first_wind_forecast["timestamp"] == now.isoformat()
    assert first_wind_forecast["value"] == 3500
    assert wind_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert ATTR_NEXT_VALID_FROM not in wind_attrs

    wind_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolWindpowerNowSensor))
    wind_now_attrs = wind_now.extra_state_attributes
    assert wind_now.native_value == 3500
    assert wind_now_attrs[ATTR_TIMESTAMP] == now.isoformat()
    assert wind_now_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"

    cheapest_entities = [
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestWindowSensor)
    ]
    assert len(cheapest_entities) == len(CHEAPEST_WINDOW_HOURS)

    by_duration = {
        entity.extra_state_attributes[ATTR_WINDOW_DURATION]: entity for entity in cheapest_entities
    }
    assert set(by_duration) == set(CHEAPEST_WINDOW_HOURS)

    three_hour_sensor = by_duration[3]
    three_attrs = three_hour_sensor.extra_state_attributes
    three_window = cheapest_windows[3]
    assert three_window is not None
    assert three_hour_sensor.native_value == pytest.approx(round(three_window.average, 1))
    assert three_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert three_attrs[ATTR_WINDOW_START] == three_window.start.isoformat()
    assert datetime.fromisoformat(three_attrs[ATTR_WINDOW_START]) >= next_window_anchor
    assert three_attrs[ATTR_WINDOW_END] == three_window.end.isoformat()
    assert three_attrs[ATTR_WINDOW_DURATION] == 3
    assert len(three_attrs[ATTR_WINDOW_POINTS]) == len(three_window.points)
    first_point_value = three_attrs[ATTR_WINDOW_POINTS][0]["value"]
    assert first_point_value == pytest.approx(round(three_window.points[0].value, 1))

    six_hour_sensor = by_duration[6]
    six_attrs = six_hour_sensor.extra_state_attributes
    six_window = cheapest_windows[6]
    assert six_window is not None
    assert six_hour_sensor.native_value == pytest.approx(round(six_window.average, 1))
    assert datetime.fromisoformat(six_attrs[ATTR_WINDOW_START]) >= next_window_anchor
    assert len(six_attrs[ATTR_WINDOW_POINTS]) == len(six_window.points)

    twelve_hour_sensor = by_duration[12]
    twelve_attrs = twelve_hour_sensor.extra_state_attributes
    twelve_window = cheapest_windows[12]
    assert twelve_window is not None
    assert twelve_hour_sensor.native_value == pytest.approx(round(twelve_window.average, 1))
    assert datetime.fromisoformat(twelve_attrs[ATTR_WINDOW_START]) >= next_window_anchor
    assert len(twelve_attrs[ATTR_WINDOW_POINTS]) == len(twelve_window.points)

    narrations = {
        entity.extra_state_attributes[ATTR_LANGUAGE]: entity
        for entity in added
        if isinstance(entity, sensor.NordpoolNarrationSensor)
    }
    assert set(narrations) == set(NARRATION_LANGUAGES)
    fi_sensor = narrations["fi"]
    fi_attrs = fi_sensor.extra_state_attributes
    assert fi_sensor.native_value == narration_section["fi"]["summary"]
    assert fi_attrs[ATTR_NARRATION_SUMMARY] == narration_section["fi"]["summary"]
    assert fi_attrs[ATTR_NARRATION_CONTENT] == narration_section["fi"]["content"]
    assert fi_attrs[ATTR_SOURCE_URL] == narration_section["fi"]["source"]
    assert fi_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    en_sensor = narrations["en"]
    en_attrs = en_sensor.extra_state_attributes
    assert en_sensor.native_value == narration_section["en"]["summary"]
    assert en_attrs[ATTR_NARRATION_CONTENT] == narration_section["en"]["content"]
    assert en_attrs[ATTR_SOURCE_URL] == narration_section["en"]["source"]

    allowed_types = (
        sensor.NordpoolPriceSensor,
        sensor.NordpoolPriceNowSensor,
        sensor.NordpoolPriceNextHoursSensor,
        sensor.NordpoolWindpowerSensor,
        sensor.NordpoolWindpowerNowSensor,
        sensor.NordpoolCheapestWindowSensor,
        sensor.NordpoolNarrationSensor,
    )
    assert all(isinstance(e, allowed_types) for e in added)


@pytest.mark.asyncio
async def test_async_setup_entry_handles_missing_wind_data(hass, enable_custom_integrations) -> None:
    """Wind sensors are registered even when wind data is unavailable."""
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
        update_interval=timedelta(minutes=15),
    )

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    future_only_series = [
        _series_point(1, 5.0, now),
        _series_point(2, 6.0, now),
    ]
    forecast_start = future_only_series[0].datetime
    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": future_only_series,
                "current": None,
                "cheapest_windows": {hours: None for hours in CHEAPEST_WINDOW_HOURS},
                "forecast_start": forecast_start,
            },
            "windpower": None,
            "narration": {
                "fi": None,
                "en": None,
            },
        }
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {DATA_COORDINATOR: coordinator}

    added: list[sensor.NordpoolBaseSensor] = []
    expected_entity_count = (
        6  # price sensors + next hour sensors
        + 2  # wind sensors still registered
        + len(CHEAPEST_WINDOW_HOURS)
        + len(NARRATION_LANGUAGES)
    )

    def _add_entities(new_entities: list[Any], update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)

    assert len(added) == expected_entity_count
    assert sum(isinstance(entity, sensor.NordpoolPriceSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolPriceNowSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolWindpowerSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolWindpowerNowSensor) for entity in added) == 1
    attrs = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor)).extra_state_attributes
    assert attrs[ATTR_FORECAST_START] == forecast_start.isoformat()
    assert ATTR_NEXT_VALID_FROM not in attrs

    price_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceNowSensor))
    price_now_attrs = price_now.extra_state_attributes
    assert price_now.native_value is None
    assert price_now_attrs[ATTR_TIMESTAMP] is None
    assert price_now_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"

    price_sensor = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor))
    assert price_sensor.native_value is None

    next_price_entities = [
        entity for entity in added if isinstance(entity, sensor.NordpoolPriceNextHoursSensor)
    ]
    next_by_hours: dict[int, sensor.NordpoolPriceNextHoursSensor] = {}
    for entity in next_price_entities:
        for hours in NEXT_HOURS:
            if entity.unique_id.endswith(f"_price_next_{hours}h"):
                next_by_hours[hours] = entity
                break
    assert set(next_by_hours) == set(NEXT_HOURS)
    first_future = future_only_series[0]
    for hours, entity in next_by_hours.items():
        attrs_next = entity.extra_state_attributes
        if len(future_only_series) >= hours:
            expected_average = round(
                sum(point.value for point in future_only_series[:hours]) / hours, 1
            )
            assert entity.native_value == pytest.approx(expected_average)
            assert attrs_next[ATTR_TIMESTAMP] == first_future.datetime.isoformat()
            assert datetime.fromisoformat(attrs_next[ATTR_TIMESTAMP]) > now
        else:
            assert entity.native_value is None
            assert attrs_next[ATTR_TIMESTAMP] is None
        assert attrs_next[ATTR_RAW_SOURCE] == "https://example.com/deploy"

    wind_sensor = next(entity for entity in added if isinstance(entity, sensor.NordpoolWindpowerSensor))
    assert wind_sensor.native_value is None
    assert wind_sensor.extra_state_attributes is None

    wind_now_sensor = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolWindpowerNowSensor)
    )
    assert wind_now_sensor.native_value is None
    wind_now_attrs = wind_now_sensor.extra_state_attributes
    assert wind_now_attrs[ATTR_TIMESTAMP] is None
    assert wind_now_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"

    cheapest_entities = [
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestWindowSensor)
    ]
    assert len(cheapest_entities) == len(CHEAPEST_WINDOW_HOURS)
    for entity in cheapest_entities:
        entity_attrs = entity.extra_state_attributes
        assert entity.native_value is None
        assert entity_attrs[ATTR_WINDOW_START] is None
        assert entity_attrs[ATTR_WINDOW_END] is None
        assert entity_attrs[ATTR_WINDOW_POINTS] == []

    narration_entities = [
        entity for entity in added if isinstance(entity, sensor.NordpoolNarrationSensor)
    ]
    assert len(narration_entities) == len(NARRATION_LANGUAGES)
    for entity in narration_entities:
        attrs = entity.extra_state_attributes
        assert attrs[ATTR_LANGUAGE] in NARRATION_LANGUAGES
        assert attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
        assert ATTR_NARRATION_CONTENT not in attrs
        assert ATTR_SOURCE_URL not in attrs
    # Only expected entity classes were created
    allowed_types = (
        sensor.NordpoolPriceSensor,
        sensor.NordpoolPriceNowSensor,
        sensor.NordpoolPriceNextHoursSensor,
        sensor.NordpoolWindpowerSensor,
        sensor.NordpoolWindpowerNowSensor,
        sensor.NordpoolCheapestWindowSensor,
        sensor.NordpoolNarrationSensor,
    )
    assert all(isinstance(entity, allowed_types) for entity in added)
