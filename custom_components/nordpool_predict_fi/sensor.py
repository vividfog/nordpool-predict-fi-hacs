from __future__ import annotations

#region sensor

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_FORECAST,
    ATTR_LANGUAGE,
    ATTR_NARRATION_CONTENT,
    ATTR_NARRATION_SUMMARY,
    ATTR_RAW_SOURCE,
    ATTR_SOURCE_URL,
    ATTR_TIMESTAMP,
    ATTR_WIND_FORECAST,
    ATTR_WINDOW_DURATION,
    ATTR_WINDOW_END,
    ATTR_WINDOW_POINTS,
    ATTR_WINDOW_START,
    CHEAPEST_WINDOW_HOURS,
    DATA_COORDINATOR,
    DOMAIN,
    NARRATION_LANGUAGES,
    NARRATION_LANGUAGE_NAMES,
    NEXT_HOURS,
)
from .coordinator import NordpoolPredictCoordinator, PriceWindow, SeriesPoint


#region _setup
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: NordpoolPredictCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities: list[SensorEntity] = [
        NordpoolPriceSensor(coordinator, entry),
        NordpoolPriceNowSensor(coordinator, entry),
    ]
    entities.extend(
        NordpoolPriceNextHoursSensor(coordinator, entry, hours) for hours in NEXT_HOURS
    )
    entities.extend(
        NordpoolCheapestWindowSensor(coordinator, entry, hours) for hours in CHEAPEST_WINDOW_HOURS
    )
    entities.extend(
        (
            NordpoolWindpowerSensor(coordinator, entry),
            NordpoolWindpowerNowSensor(coordinator, entry),
        )
    )

    entities.extend(
        NordpoolNarrationSensor(coordinator, entry, language) for language in NARRATION_LANGUAGES
    )

    async_add_entities(entities)


#region _base
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

    def _build_forecast_attributes(
        self,
        series: list[SeriesPoint],
        decimals: int | None = None,
    ) -> list[Mapping[str, Any]]:
        return [
            {
                "timestamp": point.datetime.isoformat(),
                "value": self._rounded_value(point.value, decimals),
            }
            for point in series
        ]

    def _price_section(self) -> Mapping[str, Any] | None:
        data = self.coordinator.data or {}
        section = data.get("price")
        if isinstance(section, Mapping):
            return section
        return None

    def _cheapest_window(self, hours: int) -> PriceWindow | None:
        section = self._price_section()
        if not section:
            return None
        windows = section.get("cheapest_windows")
        if not isinstance(windows, Mapping):
            return None
        window = windows.get(hours)
        if isinstance(window, PriceWindow):
            return window
        return None

    def _price_series(self) -> list[SeriesPoint]:
        section = self._price_section()
        if not section:
            return []
        series = section.get("forecast")
        if not isinstance(series, list):
            return []
        return [point for point in series if isinstance(point, SeriesPoint)]

    def _future_point(self, hours_ahead: int) -> SeriesPoint | None:
        series = self._price_series()
        if not series:
            return None
        now = getattr(self.coordinator, "current_time", None)
        if now is None:
            now = datetime.now(timezone.utc)
        target_time = now + timedelta(hours=hours_ahead)
        # Find the point closest to target_time but >= target_time
        for point in series:
            if point.datetime >= target_time:
                return point
        return None

    def _average_next_hours(self, hours: int) -> tuple[float | None, datetime | None]:
        """Calculate average price for the next X hours starting now.

        Returns a tuple of (average_price, start_timestamp).
        If insufficient data points, returns (None, None).
        """
        series = self._price_series()
        if not series:
            return None, None

        now = getattr(self.coordinator, "current_time", None)
        if now is None:
            now = datetime.now(timezone.utc)

        # Collect points strictly after now for the averaging period
        future_points = []
        for point in series:
            if point.datetime > now:
                future_points.append(point)
                if len(future_points) >= hours:
                    break

        if len(future_points) < hours:
            # Insufficient data points
            return None, None

        # Take exactly 'hours' number of points starting from the first point strictly after now
        avg_points = future_points[:hours]
        average = sum(p.value for p in avg_points) / len(avg_points)
        start_time = avg_points[0].datetime

        return average, start_time

    @staticmethod
    def _rounded_value(value: float, decimals: int | None) -> float | int:
        if decimals is None:
            return value
        rounded = round(value, decimals)
        if decimals == 0:
            return int(rounded)
        return rounded


#region _price
class NordpoolPriceSensor(NordpoolBaseSensor):
    _attr_translation_key = "price"
    _attr_icon = "mdi:chart-line"
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_price"
        self._attr_name = "Price"

    @property
    def native_value(self) -> float | None:
        current = self._series_point("current")
        return round(current.value, 1) if current else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        data = self._price_section()
        if not data:
            return None

        forecast = self._build_forecast_attributes(data.get("forecast", []), decimals=1)
        result = {
            ATTR_FORECAST: forecast,
            ATTR_RAW_SOURCE: self.coordinator.base_url,
        }
        return result

    def _series_point(self, key: str) -> SeriesPoint | None:
        section = self._price_section()
        if not section:
            return None
        value = section.get(key)
        if isinstance(value, SeriesPoint):
            return value
        return None


#region _price_now
class NordpoolPriceNowSensor(NordpoolBaseSensor):
    _attr_translation_key = "price_now"
    _attr_icon = "mdi:cash-clock"
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_price_now"
        self._attr_name = "Price Now"

    @property
    def native_value(self) -> float | None:
        point = self._latest_point()
        return round(point.value, 1) if point else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        point = self._latest_point()
        return {
            ATTR_TIMESTAMP: point.datetime.isoformat() if point else None,
            ATTR_RAW_SOURCE: self.coordinator.base_url,
        }

    def _latest_point(self) -> SeriesPoint | None:
        series = self._price_series()
        if not series:
            return None
        # Use coordinator's current_time if available, otherwise fallback to datetime.now(timezone.utc)
        now = getattr(self.coordinator, "current_time", None)
        if now is None:
            now = datetime.now(timezone.utc)
        latest: SeriesPoint | None = None
        for point in series:
            if point.datetime <= now:
                latest = point
            else:
                break
        return latest


#region _price_next
class NordpoolPriceNextHoursSensor(NordpoolBaseSensor):
    _attr_icon = "mdi:cash-clock"
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry, hours: int) -> None:
        super().__init__(coordinator, entry)
        self._hours = hours
        self._attr_translation_key = f"price_next_{hours}h"
        self._attr_unique_id = f"{entry.entry_id}_price_next_{hours}h"
        self._attr_name = f"Price Next {hours}h"

    @property
    def native_value(self) -> float | None:
        average, _ = self._average_next_hours(self._hours)
        return round(average, 1) if average is not None else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        _, start_time = self._average_next_hours(self._hours)
        return {
            ATTR_TIMESTAMP: start_time.isoformat() if start_time else None,
            ATTR_RAW_SOURCE: self.coordinator.base_url,
        }


#region _windows
class NordpoolCheapestWindowSensor(NordpoolBaseSensor):
    _attr_icon = "mdi:clock-check-outline"
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry, hours: int) -> None:
        super().__init__(coordinator, entry)
        self._hours = hours
        self._attr_translation_key = f"cheapest_{hours}h"
        self._attr_unique_id = f"{entry.entry_id}_cheapest_{hours}h"
        self._attr_name = f"Cheapest {hours}h Price Window"

    @property
    def native_value(self) -> float | None:
        window = self._cheapest_window(self._hours)
        return round(window.average, 1) if window else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        window = self._cheapest_window(self._hours)
        attributes: dict[str, Any] = {
            ATTR_RAW_SOURCE: self.coordinator.base_url,
            ATTR_WINDOW_DURATION: self._hours,
        }
        if window:
            attributes[ATTR_WINDOW_START] = window.start.isoformat()
            attributes[ATTR_WINDOW_END] = window.end.isoformat()
            attributes[ATTR_WINDOW_POINTS] = self._build_forecast_attributes(window.points, decimals=1)
        else:
            attributes[ATTR_WINDOW_START] = None
            attributes[ATTR_WINDOW_END] = None
            attributes[ATTR_WINDOW_POINTS] = []
        return attributes


#region _windpower
class NordpoolWindpowerSensor(NordpoolBaseSensor):
    _attr_translation_key = "windpower"
    _attr_icon = "mdi:weather-windy"
    _attr_native_unit_of_measurement = "MW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_windpower"
        # Compact name for canonical object_id
        self._attr_name = "Windpower"

    @property
    def native_value(self) -> float | None:
        section = self._section()
        current = section.get("current") if section else None
        if isinstance(current, SeriesPoint):
            return int(round(current.value))
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        section = self._section()
        if not section:
            return None
        series: list[SeriesPoint] = section.get("series", [])
        forecast_series = [
            point for point in series if isinstance(point, SeriesPoint)
        ]
        return {
            ATTR_WIND_FORECAST: self._build_forecast_attributes(forecast_series, decimals=0),
            ATTR_RAW_SOURCE: self.coordinator.base_url,
        }

    def _section(self) -> Mapping[str, Any] | None:
        return (self.coordinator.data or {}).get("windpower")


#region _windpower_now
class NordpoolWindpowerNowSensor(NordpoolBaseSensor):
    _attr_translation_key = "windpower_now"
    _attr_icon = "mdi:weather-windy"
    _attr_native_unit_of_measurement = "MW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_windpower_now"
        # Compact name for canonical object_id
        self._attr_name = "Windpower Now"

    @property
    def native_value(self) -> float | None:
        point = self._current_point()
        if not point:
            return None
        return int(round(point.value))

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        point = self._current_point()
        return {
            ATTR_TIMESTAMP: point.datetime.isoformat() if point else None,
            ATTR_RAW_SOURCE: self.coordinator.base_url,
        }

    def _current_point(self) -> SeriesPoint | None:
        section = (self.coordinator.data or {}).get("windpower")
        if not isinstance(section, Mapping):
            return None
        current = section.get("current")
        if isinstance(current, SeriesPoint):
            return current
        series = section.get("series")
        if isinstance(series, list):
            now = getattr(self.coordinator, "current_time", None)
            if now is None:
                now = datetime.now(timezone.utc)
            latest: SeriesPoint | None = None
            for point in series:
                if not isinstance(point, SeriesPoint):
                    continue
                if point.datetime <= now:
                    latest = point
                else:
                    break
            if latest:
                return latest
        return None


#region _narration
class NordpoolNarrationSensor(NordpoolBaseSensor):
    _attr_icon = "mdi:file-document-edit-outline"

    def __init__(self, coordinator: NordpoolPredictCoordinator, entry: ConfigEntry, language: str) -> None:
        super().__init__(coordinator, entry)
        self._language = language
        self._attr_translation_key = f"narration_{language}"
        display_language = NARRATION_LANGUAGE_NAMES.get(language, language.upper())
        self._attr_unique_id = f"{entry.entry_id}_narration_{language}"
        self._attr_name = f"Narration ({display_language})"

    @property
    def native_value(self) -> str | None:
        section = self._section()
        if not section:
            return None
        summary = section.get("summary")
        if isinstance(summary, str) and summary:
            return summary
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        section = self._section()
        attributes: dict[str, Any] = {
            ATTR_LANGUAGE: self._language,
            ATTR_RAW_SOURCE: self.coordinator.base_url,
        }
        if not section:
            return attributes
        summary = section.get("summary")
        content = section.get("content")
        source = section.get("source")
        if isinstance(summary, str) and summary:
            attributes[ATTR_NARRATION_SUMMARY] = summary
        if isinstance(content, str) and content:
            attributes[ATTR_NARRATION_CONTENT] = content
        if isinstance(source, str) and source:
            attributes[ATTR_SOURCE_URL] = source
        return attributes

    def _section(self) -> Mapping[str, Any] | None:
        data = self.coordinator.data or {}
        narration = data.get("narration")
        if not isinstance(narration, Mapping):
            return None
        section = narration.get(self._language)
        if isinstance(section, Mapping):
            return section
        return None
