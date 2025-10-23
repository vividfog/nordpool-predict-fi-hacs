from __future__ import annotations

#region number

from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_EXTRA_FEES,
    ATTR_CUSTOM_WINDOW_HOURS,
    ATTR_CUSTOM_WINDOW_START_HOUR,
    ATTR_CUSTOM_WINDOW_END_HOUR,
    ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    ATTR_CHEAPEST_WINDOW_START_HOUR,
    ATTR_CHEAPEST_WINDOW_END_HOUR,
    ATTR_WINDOW_LOOKAHEAD_HOURS,
    DATA_COORDINATOR,
    DEFAULT_EXTRA_FEES_CENTS,
    DOMAIN,
    EXTRA_FEES_STEP_CENTS,
    DEFAULT_CHEAPEST_WINDOW_LOOKAHEAD_HOURS,
    DEFAULT_CHEAPEST_WINDOW_START_HOUR,
    DEFAULT_CHEAPEST_WINDOW_END_HOUR,
    DEFAULT_CUSTOM_WINDOW_HOURS,
    DEFAULT_CUSTOM_WINDOW_START_HOUR,
    DEFAULT_CUSTOM_WINDOW_END_HOUR,
    DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    MAX_CHEAPEST_WINDOW_LOOKAHEAD_HOURS,
    MAX_CHEAPEST_WINDOW_HOUR,
    MAX_CUSTOM_WINDOW_HOURS,
    MIN_CUSTOM_WINDOW_HOURS,
    MAX_CUSTOM_WINDOW_HOUR,
    MIN_CUSTOM_WINDOW_HOUR,
    MIN_CHEAPEST_WINDOW_LOOKAHEAD_HOURS,
    MIN_CHEAPEST_WINDOW_HOUR,
    MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
    MAX_EXTRA_FEES_CENTS,
    MIN_EXTRA_FEES_CENTS,
)
from .coordinator import NordpoolPredictCoordinator


#region _setup
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: NordpoolPredictCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    async_add_entities(
        [
            NordpoolExtraFeesNumber(coordinator, entry),
            NordpoolCheapestWindowLookaheadHoursNumber(coordinator, entry),
            NordpoolCheapestWindowStartHourNumber(coordinator, entry),
            NordpoolCheapestWindowEndHourNumber(coordinator, entry),
            NordpoolCustomWindowHoursNumber(coordinator, entry),
            NordpoolCustomWindowStartHourNumber(coordinator, entry),
            NordpoolCustomWindowEndHourNumber(coordinator, entry),
            NordpoolCustomWindowLookaheadHoursNumber(coordinator, entry),
        ]
    )


#region _number
class NordpoolExtraFeesNumber(CoordinatorEntity[NordpoolPredictCoordinator], RestoreNumber, NumberEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:cash-plus"
    _attr_native_min_value = MIN_EXTRA_FEES_CENTS
    _attr_native_max_value = MAX_EXTRA_FEES_CENTS
    _attr_native_step = EXTRA_FEES_STEP_CENTS
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "extra_fees"

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._value = DEFAULT_EXTRA_FEES_CENTS
        self._attr_unique_id = f"{entry.entry_id}_extra_fees"
        self._attr_name = "Extra Fees"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Nordpool Predict FI",
            manufacturer="Nordpool Predict",
        )

    @property
    def native_value(self) -> float:
        return self._value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = await self.async_get_last_number_data()
        if restored and restored.native_value is not None:
            self._value = self._clamp(restored.native_value)
        else:
            self._value = self._clamp(self.coordinator.extra_fees_cents)
        self.coordinator.set_extra_fees_cents(self._value)
        if self.entity_id and self.platform:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        self._value = self._clamp(value)
        self.coordinator.set_extra_fees_cents(self._value)
        if self.entity_id and self.platform:
            self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._value = self._clamp(self.coordinator.extra_fees_cents)
        if self.entity_id and self.platform:
            super()._handle_coordinator_update()

    def _clamp(self, value: float | None) -> float:
        if value is None:
            return DEFAULT_EXTRA_FEES_CENTS
        bounded = max(MIN_EXTRA_FEES_CENTS, min(MAX_EXTRA_FEES_CENTS, float(value)))
        step = EXTRA_FEES_STEP_CENTS
        rounded_steps = round(bounded / step)
        return round(rounded_steps * step, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_EXTRA_FEES: self._value}


class _NordpoolWindowBaseNumber(CoordinatorEntity[NordpoolPredictCoordinator], RestoreNumber, NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "h"

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._value: int = 0
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Nordpool Predict FI",
            manufacturer="Nordpool Predict",
        )

    @property
    def native_value(self) -> int:
        return self._value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = await self.async_get_last_number_data()
        restored_value = restored.native_value if restored and restored.native_value is not None else None
        self._value = self._restore_value(restored_value)
        await self._apply_value(self._value)
        if self.entity_id and self.platform:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        normalized = self._restore_value(value)
        if normalized == self._value:
            return
        self._value = normalized
        await self._apply_value(self._value)
        if self.entity_id and self.platform:
            self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._value = self._restore_value(self._read_from_coordinator())
        if self.entity_id and self.platform:
            super()._handle_coordinator_update()

    def _restore_value(self, value: float | int | None) -> int:
        raise NotImplementedError

    async def _apply_value(self, value: int) -> None:
        raise NotImplementedError

    def _read_from_coordinator(self) -> int:
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {}


class NordpoolCheapestWindowLookaheadHoursNumber(_NordpoolWindowBaseNumber):
    _attr_translation_key = "cheapest_window_lookahead_hours"
    _attr_icon = "mdi:timeline-clock-outline"
    _attr_native_min_value = MIN_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
    _attr_native_max_value = MAX_CHEAPEST_WINDOW_LOOKAHEAD_HOURS

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._value = DEFAULT_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
        self._attr_unique_id = f"{entry.entry_id}_cheapest_window_lookahead_hours"
        self._attr_name = "Cheapest Window Lookahead Hours"

    def _restore_value(self, value: float | int | None) -> int:
        if value is None:
            return DEFAULT_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CHEAPEST_WINDOW_LOOKAHEAD_HOURS
        bounded = max(
            MIN_CHEAPEST_WINDOW_LOOKAHEAD_HOURS,
            min(MAX_CHEAPEST_WINDOW_LOOKAHEAD_HOURS, coerced),
        )
        return bounded

    async def _apply_value(self, value: int) -> None:
        self.coordinator.set_cheapest_window_lookahead_hours(value)

    def _read_from_coordinator(self) -> int:
        return int(self.coordinator.cheapest_window_lookahead_hours)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_WINDOW_LOOKAHEAD_HOURS: self._value}


class NordpoolCheapestWindowStartHourNumber(_NordpoolWindowBaseNumber):
    _attr_translation_key = "cheapest_window_start_hour"
    _attr_icon = "mdi:clock-start"
    _attr_native_min_value = MIN_CHEAPEST_WINDOW_HOUR
    _attr_native_max_value = MAX_CHEAPEST_WINDOW_HOUR

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._value = DEFAULT_CHEAPEST_WINDOW_START_HOUR
        self._attr_unique_id = f"{entry.entry_id}_cheapest_window_start_hour"
        self._attr_name = "Cheapest Window Start Hour"

    def _restore_value(self, value: float | int | None) -> int:
        if value is None:
            return DEFAULT_CHEAPEST_WINDOW_START_HOUR
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CHEAPEST_WINDOW_START_HOUR
        bounded = max(MIN_CHEAPEST_WINDOW_HOUR, min(MAX_CHEAPEST_WINDOW_HOUR, coerced))
        return bounded

    async def _apply_value(self, value: int) -> None:
        self.coordinator.set_cheapest_window_start_hour(value)

    def _read_from_coordinator(self) -> int:
        return int(self.coordinator.cheapest_window_start_hour)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_CHEAPEST_WINDOW_START_HOUR: self._value}


class NordpoolCheapestWindowEndHourNumber(_NordpoolWindowBaseNumber):
    _attr_translation_key = "cheapest_window_end_hour"
    _attr_icon = "mdi:clock-end"
    _attr_native_min_value = MIN_CHEAPEST_WINDOW_HOUR
    _attr_native_max_value = MAX_CHEAPEST_WINDOW_HOUR

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._value = DEFAULT_CHEAPEST_WINDOW_END_HOUR
        self._attr_unique_id = f"{entry.entry_id}_cheapest_window_end_hour"
        self._attr_name = "Cheapest Window End Hour"

    def _restore_value(self, value: float | int | None) -> int:
        if value is None:
            return DEFAULT_CHEAPEST_WINDOW_END_HOUR
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CHEAPEST_WINDOW_END_HOUR
        bounded = max(MIN_CHEAPEST_WINDOW_HOUR, min(MAX_CHEAPEST_WINDOW_HOUR, coerced))
        return bounded

    async def _apply_value(self, value: int) -> None:
        self.coordinator.set_cheapest_window_end_hour(value)

    def _read_from_coordinator(self) -> int:
        return int(self.coordinator.cheapest_window_end_hour)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_CHEAPEST_WINDOW_END_HOUR: self._value}


class NordpoolCustomWindowHoursNumber(_NordpoolWindowBaseNumber):
    _attr_translation_key = "custom_window_hours"
    _attr_icon = "mdi:clock-time-four-outline"
    _attr_native_min_value = MIN_CUSTOM_WINDOW_HOURS
    _attr_native_max_value = MAX_CUSTOM_WINDOW_HOURS

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._value = DEFAULT_CUSTOM_WINDOW_HOURS
        self._attr_unique_id = f"{entry.entry_id}_custom_window_hours"
        self._attr_name = "Custom Window Hours"

    def _restore_value(self, value: float | int | None) -> int:
        if value is None:
            return DEFAULT_CUSTOM_WINDOW_HOURS
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CUSTOM_WINDOW_HOURS
        bounded = max(MIN_CUSTOM_WINDOW_HOURS, min(MAX_CUSTOM_WINDOW_HOURS, coerced))
        return bounded

    async def _apply_value(self, value: int) -> None:
        self.coordinator.set_custom_window_hours(value)

    def _read_from_coordinator(self) -> int:
        return int(self.coordinator.custom_window_hours)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_CUSTOM_WINDOW_HOURS: self._value}


class NordpoolCustomWindowStartHourNumber(_NordpoolWindowBaseNumber):
    _attr_translation_key = "custom_window_start_hour"
    _attr_icon = "mdi:clock-start"
    _attr_native_min_value = MIN_CUSTOM_WINDOW_HOUR
    _attr_native_max_value = MAX_CUSTOM_WINDOW_HOUR

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._value = DEFAULT_CUSTOM_WINDOW_START_HOUR
        self._attr_unique_id = f"{entry.entry_id}_custom_window_start_hour"
        self._attr_name = "Custom Window Start Hour"

    def _restore_value(self, value: float | int | None) -> int:
        if value is None:
            return DEFAULT_CUSTOM_WINDOW_START_HOUR
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CUSTOM_WINDOW_START_HOUR
        bounded = max(MIN_CUSTOM_WINDOW_HOUR, min(MAX_CUSTOM_WINDOW_HOUR, coerced))
        return bounded

    async def _apply_value(self, value: int) -> None:
        self.coordinator.set_custom_window_start_hour(value)

    def _read_from_coordinator(self) -> int:
        return int(self.coordinator.custom_window_start_hour)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_CUSTOM_WINDOW_START_HOUR: self._value}


class NordpoolCustomWindowEndHourNumber(_NordpoolWindowBaseNumber):
    _attr_translation_key = "custom_window_end_hour"
    _attr_icon = "mdi:clock-end"
    _attr_native_min_value = MIN_CUSTOM_WINDOW_HOUR
    _attr_native_max_value = MAX_CUSTOM_WINDOW_HOUR

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._value = DEFAULT_CUSTOM_WINDOW_END_HOUR
        self._attr_unique_id = f"{entry.entry_id}_custom_window_end_hour"
        self._attr_name = "Custom Window End Hour"

    def _restore_value(self, value: float | int | None) -> int:
        if value is None:
            return DEFAULT_CUSTOM_WINDOW_END_HOUR
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CUSTOM_WINDOW_END_HOUR
        bounded = max(MIN_CUSTOM_WINDOW_HOUR, min(MAX_CUSTOM_WINDOW_HOUR, coerced))
        return bounded

    async def _apply_value(self, value: int) -> None:
        self.coordinator.set_custom_window_end_hour(value)

    def _read_from_coordinator(self) -> int:
        return int(self.coordinator.custom_window_end_hour)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_CUSTOM_WINDOW_END_HOUR: self._value}


class NordpoolCustomWindowLookaheadHoursNumber(_NordpoolWindowBaseNumber):
    _attr_translation_key = "custom_window_lookahead_hours"
    _attr_icon = "mdi:clock-fast"
    _attr_native_min_value = MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS
    _attr_native_max_value = MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._value = DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS
        self._attr_unique_id = f"{entry.entry_id}_custom_window_lookahead_hours"
        self._attr_name = "Custom Window Lookahead Hours"

    def _restore_value(self, value: float | int | None) -> int:
        if value is None:
            return DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS
        try:
            coerced = int(round(float(value)))
        except (TypeError, ValueError):
            coerced = DEFAULT_CUSTOM_WINDOW_LOOKAHEAD_HOURS
        bounded = max(
            MIN_CUSTOM_WINDOW_LOOKAHEAD_HOURS,
            min(MAX_CUSTOM_WINDOW_LOOKAHEAD_HOURS, coerced),
        )
        return bounded

    async def _apply_value(self, value: int) -> None:
        self.coordinator.set_custom_window_lookahead_hours(value)

    def _read_from_coordinator(self) -> int:
        return int(self.coordinator.custom_window_lookahead_hours)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_CUSTOM_WINDOW_LOOKAHEAD_HOURS: self._value}
