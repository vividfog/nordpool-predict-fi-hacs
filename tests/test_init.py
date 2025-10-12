from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.nordpool_predict_fi import _runtime_entry_config
from custom_components.nordpool_predict_fi.const import (
    CONF_BASE_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
)


def _entry(data: dict, options: dict) -> SimpleNamespace:
    return SimpleNamespace(data=data, options=options)


def test_runtime_entry_config_normalizes_values() -> None:
    entry = _entry(
        {
            CONF_BASE_URL: " https://example.com/deploy/ ",
            CONF_UPDATE_INTERVAL: 0,
        },
        {},
    )

    result = _runtime_entry_config(entry)

    assert result[CONF_BASE_URL] == "https://example.com/deploy"
    assert result[CONF_UPDATE_INTERVAL] == timedelta(minutes=1)


def test_runtime_entry_config_prefers_options_over_data() -> None:
    entry = _entry(
        {
            CONF_BASE_URL: "https://example.com/deploy",
            CONF_UPDATE_INTERVAL: timedelta(minutes=45),
        },
        {
            CONF_UPDATE_INTERVAL: 10,
        },
    )

    result = _runtime_entry_config(entry)

    assert result[CONF_BASE_URL] == "https://example.com/deploy"
    assert result[CONF_UPDATE_INTERVAL] == timedelta(minutes=10)


@pytest.mark.parametrize("raw_base", ["", "   ", "https://example.com/deploy/"])
def test_runtime_entry_config_handles_defaults(raw_base: str) -> None:
    entry = _entry(
        {
            CONF_BASE_URL: raw_base,
        },
        {},
    )

    result = _runtime_entry_config(entry)

    expected_base = DEFAULT_BASE_URL if not raw_base.strip() else raw_base.strip().rstrip("/")
    assert result[CONF_BASE_URL] == expected_base
    assert result[CONF_UPDATE_INTERVAL] == timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES)
