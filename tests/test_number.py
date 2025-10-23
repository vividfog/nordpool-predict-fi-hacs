from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nordpool_predict_fi import number
from custom_components.nordpool_predict_fi.const import (
    ATTR_EXTRA_FEES,
    DATA_COORDINATOR,
    DOMAIN,
    DEFAULT_CHEAPEST_WINDOW_LOOKAHEAD_HOURS,
    DEFAULT_CHEAPEST_WINDOW_END_HOUR,
    DEFAULT_CHEAPEST_WINDOW_START_HOUR,
    DEFAULT_CUSTOM_WINDOW_END_HOUR,
    DEFAULT_CUSTOM_WINDOW_HOURS,
    DEFAULT_CUSTOM_WINDOW_START_HOUR,
    DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    MAX_CHEAPEST_WINDOW_LOOKAHEAD_HOURS,
    MAX_CHEAPEST_WINDOW_HOUR,
    MAX_CUSTOM_WINDOW_HOUR,
    MAX_CUSTOM_WINDOW_HOURS,
    MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    MAX_EXTRA_FEES_CENTS,
    MIN_CHEAPEST_WINDOW_LOOKAHEAD_HOURS,
    MIN_CHEAPEST_WINDOW_HOUR,
    MIN_CUSTOM_WINDOW_HOUR,
    MIN_CUSTOM_WINDOW_HOURS,
    MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    MIN_EXTRA_FEES_CENTS,
)
from custom_components.nordpool_predict_fi.coordinator import NordpoolPredictCoordinator


@pytest.mark.asyncio
async def test_extra_fees_number_updates_coordinator(hass, enable_custom_integrations) -> None:
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
        update_interval=None,
    )

    coordinator.async_set_updated_data({})

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {DATA_COORDINATOR: coordinator}

    added: list[number.NumberEntity] = []

    def _add_entities(new_entities, update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await number.async_setup_entry(hass, entry, _add_entities)

    assert len(added) == 8

    for index, entity in enumerate(added, start=1):
        entity.hass = hass
        entity.entity_id = f"number.nordpool_predict_fi_test_{index}"
        await entity.async_added_to_hass()

    extra = next(entity for entity in added if isinstance(entity, number.NordpoolExtraFeesNumber))
    hours_number = next(
        entity for entity in added if isinstance(entity, number.NordpoolCustomWindowHoursNumber)
    )
    start_number = next(
        entity for entity in added if isinstance(entity, number.NordpoolCustomWindowStartHourNumber)
    )
    end_number = next(
        entity for entity in added if isinstance(entity, number.NordpoolCustomWindowEndHourNumber)
    )
    global_lookahead_number = next(
        entity
        for entity in added
        if isinstance(entity, number.NordpoolCheapestWindowLookaheadHoursNumber)
    )
    cheapest_start_number = next(
        entity
        for entity in added
        if isinstance(entity, number.NordpoolCheapestWindowStartHourNumber)
    )
    cheapest_end_number = next(
        entity
        for entity in added
        if isinstance(entity, number.NordpoolCheapestWindowEndHourNumber)
    )
    lookahead_number = next(
        entity
        for entity in added
        if isinstance(entity, number.NordpoolCustomWindowLookaheadHoursNumber)
    )

    assert extra.native_value == pytest.approx(0.0)
    assert coordinator.extra_fees_cents == pytest.approx(0.0)
    assert extra.extra_state_attributes[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    await extra.async_set_native_value(7.3)
    assert extra.native_value == pytest.approx(7.3)
    assert coordinator.extra_fees_cents == pytest.approx(7.3)
    assert extra.extra_state_attributes[ATTR_EXTRA_FEES] == pytest.approx(7.3)

    await extra.async_set_native_value(MAX_EXTRA_FEES_CENTS + 100.0)
    assert extra.native_value == pytest.approx(MAX_EXTRA_FEES_CENTS)
    assert coordinator.extra_fees_cents == pytest.approx(MAX_EXTRA_FEES_CENTS)

    await extra.async_set_native_value(MIN_EXTRA_FEES_CENTS - 100.0)
    assert extra.native_value == pytest.approx(MIN_EXTRA_FEES_CENTS)
    assert coordinator.extra_fees_cents == pytest.approx(MIN_EXTRA_FEES_CENTS)

    assert hours_number.native_value == DEFAULT_CUSTOM_WINDOW_HOURS
    assert coordinator.custom_window_hours == DEFAULT_CUSTOM_WINDOW_HOURS
    assert hours_number.extra_state_attributes["custom_window_hours"] == DEFAULT_CUSTOM_WINDOW_HOURS

    await hours_number.async_set_native_value(MAX_CUSTOM_WINDOW_HOURS + 10)
    assert hours_number.native_value == MAX_CUSTOM_WINDOW_HOURS
    assert coordinator.custom_window_hours == MAX_CUSTOM_WINDOW_HOURS

    await hours_number.async_set_native_value(MIN_CUSTOM_WINDOW_HOURS - 5)
    assert hours_number.native_value == MIN_CUSTOM_WINDOW_HOURS
    assert coordinator.custom_window_hours == MIN_CUSTOM_WINDOW_HOURS

    assert start_number.native_value == DEFAULT_CUSTOM_WINDOW_START_HOUR
    assert coordinator.custom_window_start_hour == DEFAULT_CUSTOM_WINDOW_START_HOUR
    await start_number.async_set_native_value(MAX_CUSTOM_WINDOW_HOUR + 3)
    assert start_number.native_value == MAX_CUSTOM_WINDOW_HOUR
    assert coordinator.custom_window_start_hour == MAX_CUSTOM_WINDOW_HOUR
    await start_number.async_set_native_value(MIN_CUSTOM_WINDOW_HOUR - 2)
    assert start_number.native_value == MIN_CUSTOM_WINDOW_HOUR
    assert coordinator.custom_window_start_hour == MIN_CUSTOM_WINDOW_HOUR

    assert end_number.native_value == DEFAULT_CUSTOM_WINDOW_END_HOUR
    assert coordinator.custom_window_end_hour == DEFAULT_CUSTOM_WINDOW_END_HOUR
    await end_number.async_set_native_value(MAX_CUSTOM_WINDOW_HOUR + 5)
    assert end_number.native_value == MAX_CUSTOM_WINDOW_HOUR
    assert coordinator.custom_window_end_hour == MAX_CUSTOM_WINDOW_HOUR
    await end_number.async_set_native_value(MIN_CUSTOM_WINDOW_HOUR - 3)
    assert end_number.native_value == MIN_CUSTOM_WINDOW_HOUR
    assert coordinator.custom_window_end_hour == MIN_CUSTOM_WINDOW_HOUR

    assert cheapest_start_number.native_value == DEFAULT_CHEAPEST_WINDOW_START_HOUR
    assert coordinator.cheapest_window_start_hour == DEFAULT_CHEAPEST_WINDOW_START_HOUR
    assert (
        cheapest_start_number.extra_state_attributes["cheapest_window_start_hour"]
        == DEFAULT_CHEAPEST_WINDOW_START_HOUR
    )

    await cheapest_start_number.async_set_native_value(MAX_CHEAPEST_WINDOW_HOUR + 4)
    assert cheapest_start_number.native_value == MAX_CHEAPEST_WINDOW_HOUR
    assert coordinator.cheapest_window_start_hour == MAX_CHEAPEST_WINDOW_HOUR
    await cheapest_start_number.async_set_native_value(MIN_CHEAPEST_WINDOW_HOUR - 3)
    assert cheapest_start_number.native_value == MIN_CHEAPEST_WINDOW_HOUR
    assert coordinator.cheapest_window_start_hour == MIN_CHEAPEST_WINDOW_HOUR

    assert cheapest_end_number.native_value == DEFAULT_CHEAPEST_WINDOW_END_HOUR
    assert coordinator.cheapest_window_end_hour == DEFAULT_CHEAPEST_WINDOW_END_HOUR
    assert (
        cheapest_end_number.extra_state_attributes["cheapest_window_end_hour"]
        == DEFAULT_CHEAPEST_WINDOW_END_HOUR
    )

    await cheapest_end_number.async_set_native_value(MAX_CHEAPEST_WINDOW_HOUR + 7)
    assert cheapest_end_number.native_value == MAX_CHEAPEST_WINDOW_HOUR
    assert coordinator.cheapest_window_end_hour == MAX_CHEAPEST_WINDOW_HOUR
    await cheapest_end_number.async_set_native_value(MIN_CHEAPEST_WINDOW_HOUR - 4)
    assert cheapest_end_number.native_value == MIN_CHEAPEST_WINDOW_HOUR
    assert coordinator.cheapest_window_end_hour == MIN_CHEAPEST_WINDOW_HOUR

    assert (
        global_lookahead_number.native_value
        == DEFAULT_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
    )
    assert (
        coordinator.cheapest_window_lookahead_hours
        == DEFAULT_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
    )
    assert (
        global_lookahead_number.extra_state_attributes["window_lookahead_hours"]
        == DEFAULT_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
    )

    await global_lookahead_number.async_set_native_value(
        MAX_CHEAPEST_WINDOW_LOOKAHEAD_HOURS + 10
    )
    assert (
        global_lookahead_number.native_value
        == MAX_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
    )
    assert (
        coordinator.cheapest_window_lookahead_hours
        == MAX_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
    )

    await global_lookahead_number.async_set_native_value(
        MIN_CHEAPEST_WINDOW_LOOKAHEAD_HOURS - 5
    )
    assert (
        global_lookahead_number.native_value
        == MIN_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
    )
    assert (
        coordinator.cheapest_window_lookahead_hours
        == MIN_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
    )

    assert lookahead_number.native_value == DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS
    assert coordinator.custom_window_lookahead_hours == DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS
    assert (
        lookahead_number.extra_state_attributes["custom_window_lookahead_hours"]
        == DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS
    )

    await lookahead_number.async_set_native_value(MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS + 10)
    assert lookahead_number.native_value == MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS
    assert coordinator.custom_window_lookahead_hours == MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS

    await lookahead_number.async_set_native_value(MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS - 5)
    assert lookahead_number.native_value == MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS
    assert coordinator.custom_window_lookahead_hours == MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS
