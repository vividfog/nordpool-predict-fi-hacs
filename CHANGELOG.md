# Changelog

All notable changes to this project are documented here. This project follows the Common Changelog style (common-changelog.org).

## 2025-10-19
### Added
- Dedicated `number.nordpool_predict_fi_extra_fees` entity to adjust a constant cents-per-kWh surcharge that applies to all price sensors.
- Daily average price sensor with full-day (00:00-23:00 Helsinki) breakdowns and a sample Markdown dashboard card.

### Changed
- Price sensors now expose `extra_fees` attributes and include the configured surcharge in forecast, now, next-hour averages, and cheapest window outputs.

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
