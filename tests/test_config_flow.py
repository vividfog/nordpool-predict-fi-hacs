from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nordpool_predict_fi.const import (
    CONF_BASE_URL,
    CONF_INCLUDE_WINDPOWER,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)


async def test_full_config_flow(hass: HomeAssistant, enable_custom_integrations, monkeypatch) -> None:
    """Test user config flow and ensure entry is created."""
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.async_setup_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.NordpoolPredictCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM

    user_input = {
        CONF_BASE_URL: DEFAULT_BASE_URL,
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_MINUTES,
        CONF_INCLUDE_WINDPOWER: True,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Nordpool Predict FI"
    assert result["data"][CONF_BASE_URL] == DEFAULT_BASE_URL
    assert result["data"][CONF_INCLUDE_WINDPOWER] is True


async def test_options_flow(hass: HomeAssistant, enable_custom_integrations, monkeypatch) -> None:
    """Ensure options flow stores overrides."""
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.async_setup_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.NordpoolPredictCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Nordpool Predict FI",
        data={
            CONF_BASE_URL: DEFAULT_BASE_URL,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_MINUTES,
            CONF_INCLUDE_WINDPOWER: True,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    updated = {
        CONF_BASE_URL: f"{DEFAULT_BASE_URL}/alt",
        CONF_UPDATE_INTERVAL: 45,
        CONF_INCLUDE_WINDPOWER: True,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=updated,
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPDATE_INTERVAL] == 45
    assert entry.options[CONF_INCLUDE_WINDPOWER] is True


async def test_user_flow_invalid_url(hass: HomeAssistant, enable_custom_integrations) -> None:
    """Invalid URLs should keep the form open with an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM

    invalid = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_BASE_URL: "not-a-url",
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_MINUTES,
            CONF_INCLUDE_WINDPOWER: True,
        },
    )

    assert invalid["type"] == FlowResultType.FORM
    assert invalid["errors"] == {CONF_BASE_URL: "invalid_url"}


async def test_options_flow_invalid_url(hass: HomeAssistant, enable_custom_integrations, monkeypatch) -> None:
    """Options flow should surface validation errors."""
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.async_setup_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.NordpoolPredictCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Nordpool Predict FI",
        data={
            CONF_BASE_URL: DEFAULT_BASE_URL,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_MINUTES,
            CONF_INCLUDE_WINDPOWER: True,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    invalid = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_BASE_URL: "nope",
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_MINUTES,
            CONF_INCLUDE_WINDPOWER: True,
        },
    )

    assert invalid["type"] == FlowResultType.FORM
    assert invalid["errors"] == {CONF_BASE_URL: "invalid_url"}


async def test_reconfigure_flow_prefills_defaults(hass: HomeAssistant, enable_custom_integrations, monkeypatch) -> None:
    """Reconfigure form should surface combined entry defaults."""
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.async_setup_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.NordpoolPredictCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Nordpool Predict FI",
        data={
            CONF_BASE_URL: DEFAULT_BASE_URL,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_MINUTES,
        },
        options={
            CONF_BASE_URL: f"{DEFAULT_BASE_URL}/alt",
            CONF_INCLUDE_WINDPOWER: False,
        },
    )
    entry.add_to_hass(hass)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    assert flow["type"] == FlowResultType.FORM
    defaults = flow["data_schema"]({})
    assert defaults[CONF_BASE_URL] == f"{DEFAULT_BASE_URL}/alt"
    assert defaults[CONF_UPDATE_INTERVAL] == DEFAULT_UPDATE_INTERVAL_MINUTES
    assert defaults[CONF_INCLUDE_WINDPOWER] is False


async def test_reconfigure_flow_updates_entry(hass: HomeAssistant, enable_custom_integrations, monkeypatch) -> None:
    """Reconfigure flow should normalize values before returning data."""
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.async_setup_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "custom_components.nordpool_predict_fi.coordinator.NordpoolPredictCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Nordpool Predict FI",
        data={
            CONF_BASE_URL: DEFAULT_BASE_URL,
            CONF_INCLUDE_WINDPOWER: True,
        },
        options={},
    )
    entry.add_to_hass(hass)

    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert flow["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        user_input={
            CONF_BASE_URL: f"{DEFAULT_BASE_URL}/custom/",
            CONF_UPDATE_INTERVAL: 120,
            CONF_INCLUDE_WINDPOWER: False,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == entry.title
    assert result["data"][CONF_BASE_URL] == f"{DEFAULT_BASE_URL}/custom"
    assert result["data"][CONF_UPDATE_INTERVAL] == 120
    assert result["data"][CONF_INCLUDE_WINDPOWER] is False
