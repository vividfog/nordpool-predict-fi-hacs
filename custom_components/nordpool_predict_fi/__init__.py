from __future__ import annotations

#region setup

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_BASE_URL,
    CONF_UPDATE_INTERVAL,
    DATA_COORDINATOR,
    DATA_UNSUB_LISTENER,
    DEFAULT_BASE_URL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import NordpoolPredictCoordinator

type NordpoolConfigEntry = ConfigEntry


#region _bootstrap
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


#region _entry_setup
async def async_setup_entry(hass: HomeAssistant, entry: NordpoolConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    runtime_config = _runtime_entry_config(entry)

    coordinator = NordpoolPredictCoordinator(
        hass=hass,
        entry_id=entry.entry_id,
        base_url=runtime_config[CONF_BASE_URL],
        update_interval=runtime_config[CONF_UPDATE_INTERVAL],
    )

    await coordinator.async_config_entry_first_refresh()

    unsub_options = entry.add_update_listener(async_update_entry)
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_UNSUB_LISTENER: unsub_options,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Entity_id migration: normalize narration to canonical fi/en names (idempotent).
    try:
        registry = er.async_get(hass)
        for lang in ("fi", "en"):
            unique_id = f"{entry.entry_id}_narration_{lang}"
            current_entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if not current_entity_id:
                continue
            desired_entity_id = f"sensor.{DOMAIN}_narration_{lang}"
            if current_entity_id == desired_entity_id:
                continue
            # Rename only if target entity_id is free
            if registry.async_get(desired_entity_id) is None:
                registry.async_update_entity(current_entity_id, new_entity_id=desired_entity_id)
        # Entity_id migration: normalize wind sensors to canonical windpower names.
        for suffix in ("windpower", "windpower_now"):
            unique_id = f"{entry.entry_id}_{suffix}"
            current_entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if not current_entity_id:
                continue
            desired_entity_id = f"sensor.{DOMAIN}_{suffix}"
            if current_entity_id == desired_entity_id:
                continue
            if registry.async_get(desired_entity_id) is None:
                registry.async_update_entity(current_entity_id, new_entity_id=desired_entity_id)
    except Exception:
        # Never fail setup due to migration
        pass
    return True


#region _entry_unload
async def async_unload_entry(hass: HomeAssistant, entry: NordpoolConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        stored = hass.data[DOMAIN].pop(entry.entry_id, None)
        if stored and (unsub := stored.get(DATA_UNSUB_LISTENER)):
            unsub()
    return unload_ok


#region _options_update
async def async_update_entry(hass: HomeAssistant, entry: NordpoolConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


#region _config
def _runtime_entry_config(entry: NordpoolConfigEntry) -> Mapping[str, Any]:
    result: dict[str, Any] = {
        CONF_BASE_URL: DEFAULT_BASE_URL,
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
    }

    def _normalize(data: Mapping[str, Any]) -> None:
        if CONF_BASE_URL in data:
            base_url = str(data[CONF_BASE_URL]).strip()
            if base_url.endswith("/"):
                base_url = base_url[:-1]
            result[CONF_BASE_URL] = base_url or DEFAULT_BASE_URL
        if CONF_UPDATE_INTERVAL in data:
            minutes = data[CONF_UPDATE_INTERVAL]
            if isinstance(minutes, timedelta):
                total_minutes = max(int(minutes.total_seconds() / 60), 1)
            else:
                total_minutes = max(int(minutes), 1)
            result[CONF_UPDATE_INTERVAL] = timedelta(minutes=total_minutes)

    _normalize(entry.data)
    _normalize(entry.options)

    if result[CONF_UPDATE_INTERVAL] == DEFAULT_UPDATE_INTERVAL and CONF_UPDATE_INTERVAL not in entry.data:
        result[CONF_UPDATE_INTERVAL] = timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES)

    return result
