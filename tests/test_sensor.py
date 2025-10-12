from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nordpool_predict_fi import sensor
from custom_components.nordpool_predict_fi.const import (
    ATTR_FORECAST,
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
    values = [12.3, 9.5, 8.0, 8.5, 7.0, 7.1, 9.2, 10.5, 11.0, 12.5, 13.0, 14.0]
    forecast_series = [
        _series_point(index + 1, value, now) for index, value in enumerate(values)
    ]
    merged_price_series = [_series_point(0, values[0], now), *forecast_series]
    cheapest_windows = {
        hours: coordinator._find_cheapest_window(forecast_series, hours) for hours in CHEAPEST_WINDOW_HOURS
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
                "current": forecast_series[0],
                "cheapest_windows": cheapest_windows,
            },
            "windpower": {
                "series": [
                    _series_point(1, 3500.0, now),
                    _series_point(2, 4100.0, now),
                ],
                "current": _series_point(1, 3500.0, now),
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
    assert sum(isinstance(entity, sensor.NordpoolNarrationSensor) for entity in added) == len(
        NARRATION_LANGUAGES
    )
    price = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor))
    attrs = price.extra_state_attributes
    assert price.native_value == pytest.approx(12.3)
    assert attrs[ATTR_FORECAST][0]["value"] == pytest.approx(12.3)
    assert attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert ATTR_NEXT_VALID_FROM not in attrs

    price_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceNowSensor))
    price_now_attrs = price_now.extra_state_attributes
    assert price_now.native_value == pytest.approx(values[0])
    assert price_now_attrs[ATTR_TIMESTAMP] == merged_price_series[0].datetime.isoformat()
    assert price_now_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"

    wind = next(entity for entity in added if isinstance(entity, sensor.NordpoolWindpowerSensor))
    wind_attrs = wind.extra_state_attributes
    assert wind.native_value == 3500
    assert len(wind_attrs[ATTR_WIND_FORECAST]) == 2
    assert wind_attrs[ATTR_WIND_FORECAST][0]["value"] == 3500
    assert wind_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert ATTR_NEXT_VALID_FROM not in wind_attrs

    wind_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolWindpowerNowSensor))
    wind_now_attrs = wind_now.extra_state_attributes
    assert wind_now.native_value == 3500
    assert wind_now_attrs[ATTR_TIMESTAMP] == forecast_series[0].datetime.isoformat()
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
    expected_start = forecast_series[3].datetime
    expected_end = forecast_series[5].datetime + timedelta(hours=1)
    expected_average = round(sum(values[3:6]) / 3, 1)

    assert three_hour_sensor.native_value == expected_average
    assert three_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"
    assert three_attrs[ATTR_WINDOW_START] == expected_start.isoformat()
    assert three_attrs[ATTR_WINDOW_END] == expected_end.isoformat()
    assert three_attrs[ATTR_WINDOW_DURATION] == 3
    assert len(three_attrs[ATTR_WINDOW_POINTS]) == 3
    assert three_attrs[ATTR_WINDOW_POINTS][0]["value"] == pytest.approx(values[3])

    six_hour_sensor = by_duration[6]
    assert six_hour_sensor.native_value == round(sum(values[1:7]) / 6, 1)
    assert len(six_hour_sensor.extra_state_attributes[ATTR_WINDOW_POINTS]) == 6

    twelve_hour_sensor = by_duration[12]
    assert twelve_hour_sensor.native_value == round(sum(values) / len(values), 1)
    assert len(twelve_hour_sensor.extra_state_attributes[ATTR_WINDOW_POINTS]) == 12

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
    future_only_series = [_series_point(1, 5.0, now)]
    coordinator.async_set_updated_data(
        {
            "price": {
                "forecast": [
                    _series_point(0, 4.8, now),
                    *future_only_series,
                ],
                "current": future_only_series[0],
                "cheapest_windows": {
                    hours: coordinator._find_cheapest_window(future_only_series, hours)
                    for hours in CHEAPEST_WINDOW_HOURS
                },
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
        6  # NordpoolPriceSensor, NordpoolPriceNowSensor, and 4 next hour sensors
        + len(CHEAPEST_WINDOW_HOURS)  # NordpoolCheapestWindowSensor(s)
        + len(NARRATION_LANGUAGES)  # NordpoolNarrationSensor(s)
    )

    def _add_entities(new_entities: list[Any], update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)

    assert len(added) == expected_entity_count
    assert sum(isinstance(entity, sensor.NordpoolPriceSensor) for entity in added) == 1
    assert sum(isinstance(entity, sensor.NordpoolPriceNowSensor) for entity in added) == 1
    attrs = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceSensor)).extra_state_attributes
    assert ATTR_NEXT_VALID_FROM not in attrs

    price_now = next(entity for entity in added if isinstance(entity, sensor.NordpoolPriceNowSensor))
    price_now_attrs = price_now.extra_state_attributes
    assert price_now.native_value == pytest.approx(4.8)
    assert price_now_attrs[ATTR_TIMESTAMP] == _series_point(0, 4.8, now).datetime.isoformat()
    assert price_now_attrs[ATTR_RAW_SOURCE] == "https://example.com/deploy"

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
