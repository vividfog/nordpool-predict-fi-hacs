# Changelog

All notable changes to this project are documented here. This project follows the Common Changelog style (common-changelog.org).

## 2025-10-23
### Changed
- Shared cheapest window start/end hours now limit only the starting hour, so longer 6 h and 12 h windows remain available while still honoring the configured mask.
- Custom cheapest window uses the same start-hour-only mask, keeping behaviour consistent with the fixed windows while still honouring wraparound masks.
- Coordinator refresh metadata includes the shared start/end hours immediately, keeping sensor attributes accurate after each update cycle.
- Fixed cheapest windows now respect the shared start/end hour mask and surface those hours as sensor attributes.
- Number entities for the shared cheapest window start and end hours applied across the 3/6/12-hour sensors.

## 2025-10-19
### Added
- Dedicated `number.nordpool_predict_fi_extra_fees` entity to adjust a constant cents-per-kWh surcharge that applies to all price sensors.
- Daily average price sensor with full-day (00:00-23:00 Helsinki) breakdowns and paired Lovelace cards (markdown + button-card) showing daily min/avg/max.
- Boolean cheapest-window helper sensors (`sensor.nordpool_predict_fi_cheapest_{3|6|12}h_window_active`) that report when the chosen window currently includes the present hour.
- Custom cheapest window sensor pair (`sensor.nordpool_predict_fi_cheapest_custom_price_window` / `_window_active`) plus number entities for duration and hour mask configuration.
- `number.nordpool_predict_fi_custom_window_lookahead_hours` to cap the custom cheapest window search horizon and surface the configured horizon via entity attributes.
- Shared `number.nordpool_predict_fi_cheapest_window_lookahead_hours` to bound all fixed cheapest window calculations for up to seven days ahead.

### Changed
- Price sensors now expose `extra_fees` attributes and include the configured surcharge in forecast, now, next-hour averages, and cheapest window outputs.
- Cheapest price window selection now keeps windows that began earlier in the day so automations can react immediately when a cheapest block starts, and advances to the next candidate once the active window finishes.
- Daily average price sensor now reports the mean across all available full Helsinki days and exposes `daily_average_span_start`/`daily_average_span_end` attributes for transparency.
- Custom cheapest window selection enforces the configured lookahead horizon so results never extend past the user-defined forward window.
- Cheapest window sensors (fixed + custom) expose the shared `window_lookahead_hours`/`window_lookahead_limit` attributes for transparency and obey the global lookahead cap.
- Default shared cheapest-window lookahead now starts at 168 hours to cover the full seven-day forecast range.

## 2025-10-14
### Added
- Lovelace card snippets for narration and summaries.
- Price sensor `forecast_start` attribute for marklining the forecast boundary.

### Changed
- Automatic entity ID migration for narration and windpower sensors.
- Translations updated for en, fi, sv.
- Headings/styles and chart cards refined for clarity.
- Price ApexCharts example now renders a markline at the forecast transition.

### Fixed
- Time semantics: "now" uses the latest sample at or before current time; "next X" windows start at the next full hour and exclude the current hour; show unknown when no past sample exists.

## 2025-10-13
### Added
- Chart examples with headers and color thresholds to improve readability.

### Changed
- Windpower is now treated as a non-optional series.
- Visual contrast improvements and documentation cleanup.

## 2025-10-12
### Added
- Initial core integration: price and windpower sensors and narration scaffolding.
- Cheapest rolling price windows (3h/6h/12h).
- "Next hour" price sensors.

### Changed
- Show data from Helsinki midnight onward for aligned timelines.

### Fixed
- VAT multipliers and assorted correctness fixes.
