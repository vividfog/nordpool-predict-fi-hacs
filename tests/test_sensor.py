from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nordpool_predict_fi import sensor
from custom_components.nordpool_predict_fi.const import (
    ATTR_CUSTOM_WINDOW_END_HOUR,
    ATTR_CUSTOM_WINDOW_HOURS,
    ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    ATTR_CUSTOM_WINDOW_LOOKAHEAD_LIMIT,
    ATTR_CUSTOM_WINDOW_START_HOUR,
    ATTR_DAILY_AVERAGE_SPAN_END,
    ATTR_DAILY_AVERAGE_SPAN_START,
    ATTR_DAILY_AVERAGES,
    ATTR_FORECAST,
    ATTR_FORECAST_START,
    ATTR_EXTRA_FEES,
    ATTR_LANGUAGE,
    ATTR_NARRATION_CONTENT,
    ATTR_NARRATION_SUMMARY,
    ATTR_NEXT_VALID_FROM,
    ATTR_RAW_SOURCE,
    ATTR_SOURCE_URL,
    ATTR_TIMESTAMP,
    ATTR_WIND_FORECAST,
    ATTR_WINDOW_DURATION,
    ATTR_WINDOW_LOOKAHEAD_HOURS,
    ATTR_WINDOW_LOOKAHEAD_LIMIT,
    ATTR_WINDOW_END,
    ATTR_WINDOW_POINTS,
    ATTR_WINDOW_START,
    CHEAPEST_WINDOW_HOURS,
    CUSTOM_WINDOW_KEY,
    DATA_COORDINATOR,
    DOMAIN,
    NARRATION_LANGUAGES,
    NEXT_HOURS,
)
from custom_components.nordpool_predict_fi.coordinator import (
    DailyAverage,
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
    coordinator._current_time = lambda: now
    values = [12.3, 9.5, 8.0, 8.5, 7.0, 7.1, 9.2, 10.5, 11.0, 12.5, 13.0, 14.0, 15.0]
    current_point = _series_point(0, values[0], now)
    future_values = values[1:]
    forecast_series = [
        _series_point(index + 1, value, now) for index, value in enumerate(future_values)
    ]
    merged_price_series = [current_point, *forecast_series]
    forecast_start = forecast_series[0].datetime
    earliest_start_by_hours = {
        hours: now - timedelta(hours=hours - 1) for hours in CHEAPEST_WINDOW_HOURS
    }
    cheapest_windows = {}
    cheapest_window_limit = coordinator._cheapest_window_lookahead_limit(now)
    for hours in CHEAPEST_WINDOW_HOURS:
        earliest_start = earliest_start_by_hours[hours]
        window = coordinator._find_cheapest_window(
            merged_price_series,
            hours,
            earliest_start=earliest_start,
            min_end=now,
            max_end=cheapest_window_limit,
        )
        if window is None:
            window = coordinator._find_cheapest_window(
                merged_price_series,
                hours,
                earliest_start=earliest_start,
                max_end=cheapest_window_limit,
            )
        cheapest_windows[hours] = window
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_points = [_series_point(hour, 10.0 + hour, day_start) for hour in range(24)]
    daily_average = DailyAverage(
        date=day_start.date(),
        start=day_start,
        end=day_start + timedelta(days=1),
        average=sum(point.value for point in daily_points) / len(daily_points),
        points=daily_points,
    )
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

    custom_hours = 4
    earliest_start_custom = now - timedelta(hours=custom_hours - 1)
    lookahead_limit = coordinator._custom_window_lookahead_limit(now)
    custom_window = coordinator._find_cheapest_window(
        merged_price_series,
        custom_hours,
        earliest_start=earliest_start_custom,
        min_end=now,
        max_end=lookahead_limit,
    )
    if custom_window is None:
        custom_window = coordinator._find_cheapest_window(
            merged_price_series,
            custom_hours,
            earliest_start=earliest_start_custom,
            max_end=lookahead_limit,
        )
    custom_window_entry = {
        "window": custom_window,
        "hours": custom_hours,
        "start_hour": 0,
        "end_hour": 23,
        "lookahead_hours": coordinator.custom_window_lookahead_hours,
        "lookahead_limit": lookahead_limit,
    }

    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": merged_price_series,
                "current": current_point,
                "cheapest_windows": cheapest_windows,
                "cheapest_windows_meta": {
                    "lookahead_hours": coordinator.cheapest_window_lookahead_hours,
                    "lookahead_limit": cheapest_window_limit,
                },
                CUSTOM_WINDOW_KEY: custom_window_entry,
                "forecast_start": forecast_start,
                "now": now,
                "daily_averages": [daily_average],
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
        7  # Price, Price Now, Daily Average, and 4 next hour sensors
        + 2  # NordpoolWindpowerSensor and NordpoolWindpowerNowSensor
        + 2 * len(CHEAPEST_WINDOW_HOURS)  # Cheapest window value + active sensors
        + 2  # Custom window value + active sensors
        + len(NARRATION_LANGUAGES)  # Narration sensors
    )
    assert len(added) == expected_entity_count
    assert sum(isinstance(entity, sensor.NordpoolPriceSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolPriceNowSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolPriceDailyAverageSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolWindpowerSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolWindpowerNowSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolCheapestCustomWindowSensor) for entity in added) == 1
    assert (
        sum(isinstance(entity, sensor.NordpoolCheapestCustomWindowActiveSensor) for entity in added) == 1
    )
    assert sum(isinstance(entity, sensor.NordpoolNarrationSensor) for entity in added) == len(NARRATION_LANGUAGES)
    # Assert only expected entity classes are present
    allowed_types = (
        sensor.NordpoolPriceSensor,
        sensor.NordpoolPriceNowSensor,
        sensor.NordpoolPriceDailyAverageSensor,
        sensor.NordpoolPriceNextHoursSensor,
        sensor.NordpoolWindpowerSensor,
        sensor.NordpoolWindpowerNowSensor,
        sensor.NordpoolCheapestWindowSensor,
        sensor.NordpoolCheapestWindowActiveSensor,
        sensor.NordpoolCheapestCustomWindowSensor,
        sensor.NordpoolCheapestCustomWindowActiveSensor,
        sensor.NordpoolNarrationSensor,
    )
    assert all(isinstance(entity, allowed_types) for entity in added)
    price = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor))
    attrs = price.extra_state_attributes
    assert price.native_value == pytest.approx(round(current_point.value, 1))
    assert attrs[ATTR_FORECAST][0]["value"] == pytest.approx(round(current_point.value, 1))
    assert attrs[ATTR_FORECAST_START] == forecast_start.isoformat()
    assert attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)
    assert ATTR_NEXT_VALID_FROM not in attrs

    price_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceNowSensor))
    price_now_attrs = price_now.extra_state_attributes
    assert price_now.native_value == pytest.approx(round(current_point.value, 1))
    assert price_now_attrs[ATTR_TIMESTAMP] == current_point.datetime.isoformat()
    assert price_now_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert price_now_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    daily_sensor = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolPriceDailyAverageSensor)
    )
    daily_attrs = daily_sensor.extra_state_attributes
    expected_daily_value = round(daily_average.average, 1)
    assert daily_sensor.native_value == pytest.approx(expected_daily_value)
    assert daily_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert daily_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)
    daily_entries = daily_attrs[ATTR_DAILY_AVERAGES]
    assert len(daily_entries) == 1
    first_entry = daily_entries[0]
    assert first_entry["date"] == daily_average.date.isoformat()
    assert first_entry["average"] == pytest.approx(expected_daily_value)
    assert first_entry["hours"] == len(daily_average.points)
    assert first_entry["points"][0]["timestamp"] == daily_average.points[0].datetime.isoformat()
    assert first_entry["points"][0]["value"] == pytest.approx(round(daily_average.points[0].value, 1))

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
        assert attrs_next[ATTR_EXTRA_FEES] == pytest.approx(0.0)

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
    assert datetime.fromisoformat(three_attrs[ATTR_WINDOW_START]) >= earliest_start_by_hours[3]
    assert three_attrs[ATTR_WINDOW_END] == three_window.end.isoformat()
    assert three_attrs[ATTR_WINDOW_DURATION] == 3
    assert len(three_attrs[ATTR_WINDOW_POINTS]) == len(three_window.points)
    first_point_value = three_attrs[ATTR_WINDOW_POINTS][0]["value"]
    assert first_point_value == pytest.approx(round(three_window.points[0].value, 1))
    assert three_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)
    assert (
        three_attrs[ATTR_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.cheapest_window_lookahead_hours
    )
    assert three_attrs[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit.isoformat()

    six_hour_sensor = by_duration[6]
    six_attrs = six_hour_sensor.extra_state_attributes
    six_window = cheapest_windows[6]
    assert six_window is not None
    assert six_hour_sensor.native_value == pytest.approx(round(six_window.average, 1))
    assert datetime.fromisoformat(six_attrs[ATTR_WINDOW_START]) >= earliest_start_by_hours[6]
    assert len(six_attrs[ATTR_WINDOW_POINTS]) == len(six_window.points)
    assert six_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)
    assert (
        six_attrs[ATTR_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.cheapest_window_lookahead_hours
    )
    assert six_attrs[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit.isoformat()

    twelve_hour_sensor = by_duration[12]
    twelve_attrs = twelve_hour_sensor.extra_state_attributes
    twelve_window = cheapest_windows[12]
    assert twelve_window is not None
    assert twelve_hour_sensor.native_value == pytest.approx(round(twelve_window.average, 1))
    assert datetime.fromisoformat(twelve_attrs[ATTR_WINDOW_START]) >= earliest_start_by_hours[12]
    assert len(twelve_attrs[ATTR_WINDOW_POINTS]) == len(twelve_window.points)
    assert twelve_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)
    assert (
        twelve_attrs[ATTR_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.cheapest_window_lookahead_hours
    )
    assert twelve_attrs[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit.isoformat()

    active_entities = [
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestWindowActiveSensor)
    ]
    assert len(active_entities) == len(CHEAPEST_WINDOW_HOURS)
    active_by_duration = {
        entity.extra_state_attributes[ATTR_WINDOW_DURATION]: entity for entity in active_entities
    }
    assert set(active_by_duration) == set(CHEAPEST_WINDOW_HOURS)
    for hours, entity in active_by_duration.items():
        window = cheapest_windows[hours]
        expected_active = bool(window and window.start <= now < window.end)
        assert entity.native_value is expected_active
        attrs_active = entity.extra_state_attributes
        assert attrs_active[ATTR_WINDOW_DURATION] == hours
        assert attrs_active[ATTR_RAW_SOURCE] == "https://example.com/deploy"
        if window:
            assert attrs_active[ATTR_WINDOW_START] == window.start.isoformat()
            assert attrs_active[ATTR_WINDOW_END] == window.end.isoformat()
            assert attrs_active[ATTR_WINDOW_POINTS]
        else:
            assert attrs_active[ATTR_WINDOW_START] is None
            assert attrs_active[ATTR_WINDOW_END] is None
            assert attrs_active[ATTR_WINDOW_POINTS] == []
        assert attrs_active[ATTR_EXTRA_FEES] == pytest.approx(0.0)
        assert (
            attrs_active[ATTR_WINDOW_LOOKAHEAD_HOURS]
            == coordinator.cheapest_window_lookahead_hours
        )
        assert attrs_active[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit.isoformat()

    custom_sensor = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestCustomWindowSensor)
    )
    custom_attrs = custom_sensor.extra_state_attributes
    assert custom_attrs[ATTR_CUSTOM_WINDOW_HOURS] == custom_hours
    assert custom_attrs[ATTR_CUSTOM_WINDOW_START_HOUR] == 0
    assert custom_attrs[ATTR_CUSTOM_WINDOW_END_HOUR] == 23
    assert custom_attrs[ATTR_WINDOW_DURATION] == custom_hours
    assert (
        custom_attrs[ATTR_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.cheapest_window_lookahead_hours
    )
    assert custom_attrs[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit.isoformat()
    if custom_window:
        assert custom_sensor.native_value == pytest.approx(round(custom_window.average, 1))
        assert custom_attrs[ATTR_WINDOW_START] == custom_window.start.isoformat()
        assert custom_attrs[ATTR_WINDOW_END] == custom_window.end.isoformat()
        assert len(custom_attrs[ATTR_WINDOW_POINTS]) == len(custom_window.points)
    else:
        assert custom_sensor.native_value is None
        assert custom_attrs[ATTR_WINDOW_START] is None
        assert custom_attrs[ATTR_WINDOW_END] is None
        assert custom_attrs[ATTR_WINDOW_POINTS] == []
    assert custom_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert custom_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    custom_active = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestCustomWindowActiveSensor)
    )
    custom_active_attrs = custom_active.extra_state_attributes
    expected_custom_active = bool(custom_window and custom_window.start <= now < custom_window.end)
    assert custom_active.native_value is expected_custom_active
    assert custom_active_attrs[ATTR_CUSTOM_WINDOW_HOURS] == custom_hours
    assert custom_active_attrs[ATTR_CUSTOM_WINDOW_START_HOUR] == 0
    assert custom_active_attrs[ATTR_CUSTOM_WINDOW_END_HOUR] == 23
    assert custom_active_attrs[ATTR_WINDOW_DURATION] == custom_hours
    if custom_window:
        assert custom_active_attrs[ATTR_WINDOW_START] == custom_window.start.isoformat()
        assert custom_active_attrs[ATTR_WINDOW_END] == custom_window.end.isoformat()
        assert custom_active_attrs[ATTR_WINDOW_POINTS]
    else:
        assert custom_active_attrs[ATTR_WINDOW_START] is None
        assert custom_active_attrs[ATTR_WINDOW_END] is None
        assert custom_active_attrs[ATTR_WINDOW_POINTS] == []
    assert custom_active_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert custom_active_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)
    assert (
        custom_active_attrs[ATTR_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.cheapest_window_lookahead_hours
    )
    assert (
        custom_active_attrs[ATTR_WINDOW_LOOKAHEAD_LIMIT]
        == cheapest_window_limit.isoformat()
    )

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


@pytest.mark.asyncio
async def test_price_entities_apply_extra_fees(hass, enable_custom_integrations) -> None:
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
        update_interval=timedelta(minutes=30),
    )

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    values = [15.0, 10.0, 8.0, 12.0, 9.0, 11.0]
    current_point = _series_point(0, values[0], now)
    forecast_series = [_series_point(index + 1, value, now) for index, value in enumerate(values[1:])]
    merged_price_series = [current_point, *forecast_series]
    earliest_start_by_hours = {
        hours: now - timedelta(hours=hours - 1) for hours in CHEAPEST_WINDOW_HOURS
    }
    cheapest_windows = {}
    cheapest_window_limit = coordinator._cheapest_window_lookahead_limit(now)
    for hours in CHEAPEST_WINDOW_HOURS:
        earliest_start = earliest_start_by_hours[hours]
        window = coordinator._find_cheapest_window(
            merged_price_series,
            hours,
            earliest_start=earliest_start,
            min_end=now,
            max_end=cheapest_window_limit,
        )
        if window is None:
            window = coordinator._find_cheapest_window(
                merged_price_series,
                hours,
                earliest_start=earliest_start,
                max_end=cheapest_window_limit,
            )
        cheapest_windows[hours] = window
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_points = [_series_point(hour, 20.0 + hour, day_start) for hour in range(24)]
    daily_average = DailyAverage(
        date=day_start.date(),
        start=day_start,
        end=day_start + timedelta(days=1),
        average=sum(point.value for point in daily_points) / len(daily_points),
        points=daily_points,
    )

    custom_hours = 4
    earliest_start_custom = now - timedelta(hours=custom_hours - 1)
    lookahead_limit = coordinator._custom_window_lookahead_limit(now)
    custom_window = coordinator._find_cheapest_window(
        merged_price_series,
        custom_hours,
        earliest_start=earliest_start_custom,
        min_end=now,
        max_end=lookahead_limit,
    )
    if custom_window is None:
        custom_window = coordinator._find_cheapest_window(
            merged_price_series,
            custom_hours,
            earliest_start=earliest_start_custom,
            max_end=lookahead_limit,
        )
    custom_window_entry = {
        "window": custom_window,
        "hours": custom_hours,
        "start_hour": 0,
        "end_hour": 23,
        "lookahead_hours": coordinator.custom_window_lookahead_hours,
        "lookahead_limit": lookahead_limit,
    }

    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": merged_price_series,
                "current": current_point,
            "cheapest_windows": cheapest_windows,
            "cheapest_windows_meta": {
                "lookahead_hours": coordinator.cheapest_window_lookahead_hours,
                "lookahead_limit": cheapest_window_limit,
            },
                CUSTOM_WINDOW_KEY: custom_window_entry,
                "forecast_start": forecast_series[0].datetime,
                "now": now,
                "daily_averages": [daily_average],
            },
            "windpower": None,
            "narration": {
                "fi": None,
                "en": None,
            },
        }
    )

    extra_fee = 2.5
    coordinator.set_extra_fees_cents(extra_fee)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {DATA_COORDINATOR: coordinator}

    added: list[sensor.NordpoolBaseSensor] = []

    def _add_entities(new_entities: list[Any], update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)

    price_sensor = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor))
    price_attrs = price_sensor.extra_state_attributes
    assert price_sensor.native_value == pytest.approx(round(current_point.value + extra_fee, 1))
    assert price_attrs[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)
    assert price_attrs[ATTR_FORECAST][0]["value"] == pytest.approx(round(current_point.value + extra_fee, 1))

    price_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceNowSensor))
    now_attrs = price_now.extra_state_attributes
    assert price_now.native_value == pytest.approx(round(current_point.value + extra_fee, 1))
    assert now_attrs[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)

    daily_sensor = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolPriceDailyAverageSensor)
    )
    daily_attrs = daily_sensor.extra_state_attributes
    raw_daily_avg = daily_average.average
    expected_daily = round(raw_daily_avg + extra_fee, 1)
    assert daily_sensor.native_value == pytest.approx(expected_daily)
    assert daily_attrs[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)
    daily_entries = daily_attrs[ATTR_DAILY_AVERAGES]
    assert daily_entries
    first_entry = daily_entries[0]
    assert first_entry["average"] == pytest.approx(expected_daily)
    assert first_entry["points"][0]["value"] == pytest.approx(
        round(daily_average.points[0].value + extra_fee, 1)
    )
    assert daily_attrs[ATTR_DAILY_AVERAGE_SPAN_START] == daily_average.start.isoformat()
    assert daily_attrs[ATTR_DAILY_AVERAGE_SPAN_END] == daily_average.end.isoformat()

    future_values = values[1:]
    next_entities = [entity for entity in added if isinstance(entity, sensor.NordpoolPriceNextHoursSensor)]
    assert next_entities
    for entity in next_entities:
        attrs_next = entity.extra_state_attributes
        hours = next(
            size
            for size in NEXT_HOURS
            if entity.unique_id.endswith(f"_price_next_{size}h")
        )
        if len(future_values) < hours:
            assert entity.native_value is None
            assert attrs_next[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)
            continue
        raw_average = sum(future_values[:hours]) / hours
        expected = round(raw_average + extra_fee, 1)
        assert entity.native_value == pytest.approx(expected)
        assert attrs_next[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)

    cheapest_entities = [entity for entity in added if isinstance(entity, sensor.NordpoolCheapestWindowSensor)]
    assert cheapest_entities
    cheapest_window_limit_iso = cheapest_window_limit.isoformat()
    for entity in cheapest_entities:
        attrs_window = entity.extra_state_attributes
        hours = attrs_window[ATTR_WINDOW_DURATION]
        window = cheapest_windows.get(hours)
        if not window:
            continue
        expected_value = round(window.average + extra_fee, 1)
        assert entity.native_value == pytest.approx(expected_value)
        assert attrs_window[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)
        assert attrs_window[ATTR_WINDOW_POINTS]
        assert (
            attrs_window[ATTR_WINDOW_LOOKAHEAD_HOURS]
            == coordinator.cheapest_window_lookahead_hours
        )
        assert attrs_window[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit_iso
        first_point = attrs_window[ATTR_WINDOW_POINTS][0]
        assert first_point["value"] == pytest.approx(round(window.points[0].value + extra_fee, 1))

    active_entities = [
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestWindowActiveSensor)
    ]
    assert active_entities
    for entity in active_entities:
        attrs_window = entity.extra_state_attributes
        hours = attrs_window[ATTR_WINDOW_DURATION]
        window = cheapest_windows.get(hours)
        expected_active = bool(window and window.start <= now < window.end)
        assert entity.native_value is expected_active
        assert attrs_window[ATTR_WINDOW_DURATION] == hours
        assert attrs_window[ATTR_RAW_SOURCE] == "https://example.com/deploy"
        assert attrs_window[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)
        assert (
            attrs_window[ATTR_WINDOW_LOOKAHEAD_HOURS]
            == coordinator.cheapest_window_lookahead_hours
        )
        assert attrs_window[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit_iso

    custom_sensor = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestCustomWindowSensor)
    )
    custom_attrs = custom_sensor.extra_state_attributes
    assert custom_attrs[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)
    assert custom_attrs[ATTR_CUSTOM_WINDOW_HOURS] == custom_hours
    assert custom_attrs[ATTR_CUSTOM_WINDOW_START_HOUR] == 0
    assert custom_attrs[ATTR_CUSTOM_WINDOW_END_HOUR] == 23
    assert (
        custom_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.custom_window_lookahead_hours
    )
    assert (
        custom_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_LIMIT]
        == lookahead_limit.isoformat()
    )
    assert (
        custom_attrs[ATTR_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.cheapest_window_lookahead_hours
    )
    assert custom_attrs[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit_iso
    assert (
        custom_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.custom_window_lookahead_hours
    )
    assert custom_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_LIMIT] == lookahead_limit.isoformat()
    if custom_window:
        expected_value = round(custom_window.average + extra_fee, 1)
        assert custom_sensor.native_value == pytest.approx(expected_value)
        assert custom_attrs[ATTR_WINDOW_POINTS]
    else:
        assert custom_sensor.native_value is None
        assert custom_attrs[ATTR_WINDOW_POINTS] == []

    custom_active = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestCustomWindowActiveSensor)
    )
    custom_active_attrs = custom_active.extra_state_attributes
    expected_custom_active = bool(custom_window and custom_window.start <= now < custom_window.end)
    assert custom_active.native_value is expected_custom_active
    assert custom_active_attrs[ATTR_EXTRA_FEES] == pytest.approx(extra_fee)
    assert custom_active_attrs[ATTR_CUSTOM_WINDOW_HOURS] == custom_hours
    assert (
        custom_active_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.custom_window_lookahead_hours
    )
    assert (
        custom_active_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_LIMIT]
        == lookahead_limit.isoformat()
    )
    assert (
        custom_active_attrs[ATTR_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.cheapest_window_lookahead_hours
    )
    assert custom_active_attrs[ATTR_WINDOW_LOOKAHEAD_LIMIT] == cheapest_window_limit_iso
    assert (
        custom_active_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.custom_window_lookahead_hours
    )
    assert (
        custom_active_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_LIMIT]
        == lookahead_limit.isoformat()
    )


@pytest.mark.asyncio
async def test_daily_average_sensor_aggregates_full_span(hass, enable_custom_integrations) -> None:
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

    now = datetime(2024, 1, 2, 6, 0, tzinfo=timezone.utc)
    day1_start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    day2_start = datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)
    day1_points = [
        SeriesPoint(datetime=day1_start + timedelta(hours=offset), value=value)
        for offset, value in enumerate((10.0, 20.0, 30.0, 40.0))
    ]
    day2_points = [
        SeriesPoint(datetime=day2_start + timedelta(hours=offset), value=value)
        for offset, value in enumerate((15.0, 25.0, 35.0, 45.0))
    ]
    day1_average = sum(point.value for point in day1_points) / len(day1_points)
    day2_average = sum(point.value for point in day2_points) / len(day2_points)
    day1 = DailyAverage(
        date=day1_start.date(),
        start=day1_start,
        end=day1_start + timedelta(days=1),
        average=day1_average,
        points=day1_points,
    )
    day2 = DailyAverage(
        date=day2_start.date(),
        start=day2_start,
        end=day2_start + timedelta(days=1),
        average=day2_average,
        points=day2_points,
    )

    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": [*day1_points, *day2_points],
                "current": None,
                "cheapest_windows": {},
                CUSTOM_WINDOW_KEY: {
                    "window": None,
                    "hours": coordinator.custom_window_hours,
                    "start_hour": coordinator.custom_window_start_hour,
                    "end_hour": coordinator.custom_window_end_hour,
                    "lookahead_hours": coordinator.custom_window_lookahead_hours,
                    "lookahead_limit": coordinator._custom_window_lookahead_limit(now),
                },
                "forecast_start": day1_points[0].datetime,
                "now": now,
                "daily_averages": [day1, day2],
            },
            "windpower": None,
            "narration": {},
        }
    )

    coordinator.set_extra_fees_cents(1.5)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {DATA_COORDINATOR: coordinator}

    added: list[sensor.NordpoolBaseSensor] = []

    def _add_entities(new_entities: list[Any], update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)

    daily_sensor = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolPriceDailyAverageSensor)
    )
    daily_attrs = daily_sensor.extra_state_attributes

    all_points = [*day1_points, *day2_points]
    expected_average = sum(point.value for point in all_points) / len(all_points)
    expected_with_fee = round(expected_average + 1.5, 1)
    assert daily_sensor.native_value == pytest.approx(expected_with_fee)
    assert daily_attrs[ATTR_DAILY_AVERAGE_SPAN_START] == day1.start.isoformat()
    assert daily_attrs[ATTR_DAILY_AVERAGE_SPAN_END] == day2.end.isoformat()


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
                CUSTOM_WINDOW_KEY: {
                    "window": None,
                    "hours": 4,
                    "start_hour": 0,
                    "end_hour": 23,
                    "lookahead_hours": coordinator.custom_window_lookahead_hours,
                    "lookahead_limit": coordinator._custom_window_lookahead_limit(now),
                },
                "now": now,
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
        7  # price sensors + daily + next hour sensors
        + 2  # wind sensors still registered
        + 2 * len(CHEAPEST_WINDOW_HOURS)
        + 2  # custom window value + active sensors
        + len(NARRATION_LANGUAGES)
    )

    def _add_entities(new_entities: list[Any], update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)

    assert len(added) == expected_entity_count
    assert sum(isinstance(entity, sensor.NordpoolPriceSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolPriceNowSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolPriceDailyAverageSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolWindpowerSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolWindpowerNowSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolCheapestWindowSensor) for entity in added) == len(CHEAPEST_WINDOW_HOURS)
    assert sum(isinstance(entity, sensor.NordpoolCheapestWindowActiveSensor) for entity in added) == len(CHEAPEST_WINDOW_HOURS)
    assert sum(isinstance(entity, sensor.NordpoolCheapestCustomWindowSensor) for entity in added) == 1
    assert sum(
        isinstance(entity, sensor.NordpoolCheapestCustomWindowActiveSensor) for entity in added
    ) == 1
    attrs = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor)).extra_state_attributes
    assert attrs[ATTR_FORECAST_START] == forecast_start.isoformat()
    assert ATTR_NEXT_VALID_FROM not in attrs
    assert attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    price_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceNowSensor))
    price_now_attrs = price_now.extra_state_attributes
    assert price_now.native_value is None
    assert price_now_attrs[ATTR_TIMESTAMP] is None
    assert price_now_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert price_now_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    price_sensor = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor))
    assert price_sensor.native_value is None
    daily_sensor = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolPriceDailyAverageSensor)
    )
    daily_attrs = daily_sensor.extra_state_attributes
    assert daily_sensor.native_value is None
    assert daily_attrs[ATTR_DAILY_AVERAGES] == []
    assert daily_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)
    assert daily_attrs[ATTR_DAILY_AVERAGE_SPAN_START] is None
    assert daily_attrs[ATTR_DAILY_AVERAGE_SPAN_END] is None

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
        assert attrs_next[ATTR_EXTRA_FEES] == pytest.approx(0.0)

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
        assert entity_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    active_entities = [
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestWindowActiveSensor)
    ]
    assert len(active_entities) == len(CHEAPEST_WINDOW_HOURS)
    for entity in active_entities:
        attrs = entity.extra_state_attributes
        assert not entity.native_value
        assert attrs[ATTR_WINDOW_START] is None
        assert attrs[ATTR_WINDOW_END] is None
        assert attrs[ATTR_WINDOW_POINTS] == []
        assert attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    custom_sensor = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestCustomWindowSensor)
    )
    custom_attrs = custom_sensor.extra_state_attributes
    assert custom_sensor.native_value is None
    assert custom_attrs[ATTR_CUSTOM_WINDOW_HOURS] == 4
    assert custom_attrs[ATTR_CUSTOM_WINDOW_START_HOUR] == 0
    assert custom_attrs[ATTR_CUSTOM_WINDOW_END_HOUR] == 23
    assert (
        custom_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.custom_window_lookahead_hours
    )
    assert (
        custom_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_LIMIT]
        == coordinator._custom_window_lookahead_limit(now).isoformat()
    )
    assert custom_attrs[ATTR_WINDOW_POINTS] == []
    assert custom_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    custom_active = next(
        entity for entity in added if isinstance(entity, sensor.NordpoolCheapestCustomWindowActiveSensor)
    )
    custom_active_attrs = custom_active.extra_state_attributes
    assert not custom_active.native_value
    assert custom_active_attrs[ATTR_CUSTOM_WINDOW_HOURS] == 4
    assert custom_active_attrs[ATTR_CUSTOM_WINDOW_START_HOUR] == 0
    assert custom_active_attrs[ATTR_CUSTOM_WINDOW_END_HOUR] == 23
    assert (
        custom_active_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS]
        == coordinator.custom_window_lookahead_hours
    )
    assert (
        custom_active_attrs[ATTR_CUSTOM_WINDOW_LOOKAHEAD_LIMIT]
        == coordinator._custom_window_lookahead_limit(now).isoformat()
    )
    assert custom_active_attrs[ATTR_WINDOW_POINTS] == []
    assert custom_active_attrs[ATTR_EXTRA_FEES] == pytest.approx(0.0)

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
        sensor.NordpoolPriceDailyAverageSensor,
        sensor.NordpoolPriceNextHoursSensor,
        sensor.NordpoolWindpowerSensor,
        sensor.NordpoolWindpowerNowSensor,
        sensor.NordpoolCheapestWindowSensor,
        sensor.NordpoolCheapestWindowActiveSensor,
        sensor.NordpoolCheapestCustomWindowSensor,
        sensor.NordpoolCheapestCustomWindowActiveSensor,
        sensor.NordpoolNarrationSensor,
    )
    assert all(isinstance(entity, allowed_types) for entity in added)
