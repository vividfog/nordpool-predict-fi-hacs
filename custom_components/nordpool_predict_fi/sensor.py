from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_FORECAST,
    ATTR_NEXT_VALID_FROM,
    ATTR_RAW_SOURCE,
    ATTR_WIND_FORECAST,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import NordpoolPredictCoordinator, SeriesPoint


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: NordpoolPredictCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities: list[SensorEntity] = [
        NordpoolPriceSensor(coordinator, entry),
    ]

    if coordinator.include_windpower:
        entities.append(NordpoolWindpowerSensor(coordinator, entry))

    async_add_entities(entities)


class NordpoolBaseSensor(CoordinatorEntity[NordpoolPredictCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Nordpool Predict FI",
            manufacturer="Nordpool Predict",
        )

    def _build_forecast_attributes(self, series: list[SeriesPoint]) -> list[Mapping[str, Any]]:
        return [
            {
                "timestamp": point.datetime.isoformat(),
                "value": point.value,
            }
            for point in series
        ]

    def _price_section(self) -> Mapping[str, Any] | None:
        data = self.coordinator.data or {}
        section = data.get("price")
        if isinstance(section, Mapping):
            return section
        return None


class NordpoolPriceSensor(NordpoolBaseSensor):
    _attr_translation_key = "price"
    _attr_icon = "mdi:chart-line"
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_price"
        self._attr_name = "Upcoming Price"

    @property
    def native_value(self) -> float | None:
        current = self._series_point("current")
        return current.value if current else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        data = self._price_section()
        if not data:
            return None

        forecast = self._build_forecast_attributes(data.get("forecast", []))
        current = self._series_point("current")
        result = {
            ATTR_FORECAST: forecast,
            ATTR_RAW_SOURCE: self.coordinator.base_url,
        }
        result[ATTR_NEXT_VALID_FROM] = current.datetime.isoformat() if current else None
        return result

    def _series_point(self, key: str) -> SeriesPoint | None:
        section = self._price_section()
        if not section:
            return None
        value = section.get(key)
        if isinstance(value, SeriesPoint):
            return value
        return None

class NordpoolWindpowerSensor(NordpoolBaseSensor):
    _attr_translation_key = "windpower"
    _attr_icon = "mdi:weather-windy"
    _attr_native_unit_of_measurement = "MW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_windpower"
        self._attr_name = "Upcoming Wind Power"

    @property
    def native_value(self) -> float | None:
        section = self._section()
        current = section.get("current") if section else None
        if isinstance(current, SeriesPoint):
            return current.value
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        section = self._section()
        if not section:
            return None
        series: list[SeriesPoint] = section.get("series", [])
        current = section.get("current")
        return {
            ATTR_WIND_FORECAST: self._build_forecast_attributes(series),
            ATTR_RAW_SOURCE: self.coordinator.base_url,
            ATTR_NEXT_VALID_FROM: current.datetime.isoformat() if isinstance(current, SeriesPoint) else None,
        }

    def _section(self) -> Mapping[str, Any] | None:
        return (self.coordinator.data or {}).get("windpower")
