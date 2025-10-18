from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nordpool_predict_fi import number
from custom_components.nordpool_predict_fi.const import (
    ATTR_EXTRA_FEES,
    DATA_COORDINATOR,
    DOMAIN,
    MAX_EXTRA_FEES_CENTS,
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

    added: list[number.NordpoolExtraFeesNumber] = []

    def _add_entities(new_entities, update_before_add: bool = False) -> None:
        added.extend(new_entities)

    await number.async_setup_entry(hass, entry, _add_entities)

    assert len(added) == 1
    entity = added[0]
    entity.hass = hass
    await entity.async_added_to_hass()
    entity.entity_id = "number.nordpool_predict_fi_extra_fees"

    assert entity.native_value == pytest.approx(0.0)
    assert coordinator.extra_fees_cents == pytest.approx(0.0)
    assert entity.extra_state_attributes[ATTR_EXTRA_FEES] == pytest.approx(0.0)

    await entity.async_set_native_value(7.3)
    assert entity.native_value == pytest.approx(7.3)
    assert coordinator.extra_fees_cents == pytest.approx(7.3)
    assert entity.extra_state_attributes[ATTR_EXTRA_FEES] == pytest.approx(7.3)

    await entity.async_set_native_value(MAX_EXTRA_FEES_CENTS + 100.0)
    assert entity.native_value == pytest.approx(MAX_EXTRA_FEES_CENTS)
    assert coordinator.extra_fees_cents == pytest.approx(MAX_EXTRA_FEES_CENTS)

    await entity.async_set_native_value(MIN_EXTRA_FEES_CENTS - 100.0)
    assert entity.native_value == pytest.approx(MIN_EXTRA_FEES_CENTS)
    assert coordinator.extra_fees_cents == pytest.approx(MIN_EXTRA_FEES_CENTS)
