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
    DATA_COORDINATOR,
    DEFAULT_EXTRA_FEES_CENTS,
    DOMAIN,
    EXTRA_FEES_STEP_CENTS,
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

    async_add_entities([NordpoolExtraFeesNumber(coordinator, entry)])


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
