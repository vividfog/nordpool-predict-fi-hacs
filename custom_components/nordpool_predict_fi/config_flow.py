from __future__ import annotations

#region config_flow

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import CONF_BASE_URL, CONF_UPDATE_INTERVAL, DEFAULT_BASE_URL, DEFAULT_UPDATE_INTERVAL_MINUTES, DOMAIN


#region _flow
class NordpoolPredictConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._reconfigure_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: Mapping[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        defaults: Mapping[str, Any] | None = None

        if user_input is not None:
            data, errors = _validate_user_input(user_input)
            defaults = data
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Nordpool Predict FI", data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_form_schema(defaults),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: Mapping[str, Any] | None = None) -> FlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        defaults: Mapping[str, Any] | None

        if user_input is None:
            defaults = _entry_to_defaults(entry)
        else:
            data, errors = _validate_user_input(user_input)
            defaults = data
            if not errors:
                await self.async_set_unique_id(entry.unique_id or DOMAIN)
                return self.async_create_entry(title=entry.title, data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_form_schema(defaults),
            errors=errors,
        )

    def _get_reconfigure_entry(self) -> config_entries.ConfigEntry:
        if self._reconfigure_entry is not None:
            return self._reconfigure_entry
        entry_id = self.context.get("entry_id")
        if not entry_id:
            raise RuntimeError("Reconfigure flow requires a source entry")
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise RuntimeError("Reconfigure target not found")
        self._reconfigure_entry = entry
        return entry

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return NordpoolPredictOptionsFlow(config_entry)


#region _options
class NordpoolPredictOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: Mapping[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        defaults: Mapping[str, Any] | None

        if user_input is not None:
            data, errors = _validate_user_input(user_input)
            defaults = data
            if not errors:
                return self.async_create_entry(title="", data=data)
        else:
            defaults = _entry_to_defaults(self._entry)

        return self.async_show_form(step_id="init", data_schema=_form_schema(defaults), errors=errors)


#region _forms
def _form_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_BASE_URL, default=defaults.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=720)),
        }
    )


def _entry_to_defaults(entry: config_entries.ConfigEntry) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    combined.update(entry.data)
    combined.update(entry.options)
    return {
        CONF_BASE_URL: combined.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        CONF_UPDATE_INTERVAL: combined.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES),
    }


def _validate_user_input(user_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    data = dict(user_input)
    errors: dict[str, str] = {}

    raw_url = str(data.get(CONF_BASE_URL, "")).strip()
    if not raw_url:
        errors[CONF_BASE_URL] = "invalid_url"
        data[CONF_BASE_URL] = raw_url
    else:
        try:
            validated = cv.url(raw_url)
        except vol.Invalid:
            errors[CONF_BASE_URL] = "invalid_url"
            data[CONF_BASE_URL] = raw_url
        else:
            data[CONF_BASE_URL] = validated.rstrip("/")

    return data, errors
