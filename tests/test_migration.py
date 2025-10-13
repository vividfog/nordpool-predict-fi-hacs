from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers import entity_registry as er

from custom_components.nordpool_predict_fi.const import DOMAIN
from custom_components.nordpool_predict_fi import async_setup_entry as integration_setup


@pytest.mark.asyncio
async def test_entity_id_migration_normalizes_narration_and_wind_ids(
    hass, enable_custom_integrations, monkeypatch
) -> None:
    """Existing registry entries with legacy ids are renamed to canonical ids."""
    # Prevent network/refresh during setup
    async def _no_refresh(self):
        return None

    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.NordpoolPredictCoordinator.async_config_entry_first_refresh",
        _no_refresh,
    )

    # Prevent platform forwarding; migration operates on the registry alone
    async def _noop_forward(entry, platforms):
        return None

    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        _noop_forward,
    )

    entry = MockConfigEntry(domain=DOMAIN, title="Nordpool Predict FI", data={})
    entry.add_to_hass(hass)

    registry = er.async_get(hass)

    # Pre-create legacy entities with the same unique_ids the integration uses
    legacy = {
        f"{entry.entry_id}_narration_fi": "sensor.nordpool_predict_fi_narration_finnish",
        f"{entry.entry_id}_narration_en": "sensor.nordpool_predict_fi_narration_english",
        f"{entry.entry_id}_windpower": "sensor.nordpool_predict_fi_wind_power",
        f"{entry.entry_id}_windpower_now": "sensor.nordpool_predict_fi_wind_power_now",
    }

    for unique_id, entity_id in legacy.items():
        # suggested_object_id = entity_id without the domain prefix
        suggested = entity_id.split(".", 1)[1]
        registry.async_get_or_create(
            domain="sensor",
            platform=DOMAIN,
            unique_id=unique_id,
            config_entry=entry,
            suggested_object_id=suggested,
        )

    # Run integration setup which performs the migration
    ok = await integration_setup(hass, entry)
    assert ok is True

    # Assert canonical ids
    expected = {
        f"{entry.entry_id}_narration_fi": "sensor.nordpool_predict_fi_narration_fi",
        f"{entry.entry_id}_narration_en": "sensor.nordpool_predict_fi_narration_en",
        f"{entry.entry_id}_windpower": "sensor.nordpool_predict_fi_windpower",
        f"{entry.entry_id}_windpower_now": "sensor.nordpool_predict_fi_windpower_now",
    }

    for unique_id, target_entity_id in expected.items():
        resolved = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert resolved == target_entity_id
