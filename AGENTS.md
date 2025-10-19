# Nordpool Predict FI – Agent Handbook

## Snapshot
- Custom Home Assistant integration; core code under `custom_components/nordpool_predict_fi/`.
- Python 3.12 target; asynchronous I/O via Home Assistant helpers.
- External data: realized prices from [Sähkötin](https://sahkotin.fi/hours) plus forecasts from `prediction.json` and `windpower.json`.
- Integration platforms: `sensor`.
- Sample Lovelace cards in repo root (ApexCharts) for price + wind.

## Primary Modules
- `__init__.py`: sets up `DataUpdateCoordinator`, registers platforms, normalises config entry options.
- `const.py`: domain constants, default config, attribute keys.
- `coordinator.py`: fetches Sähkötin CSV + JSON artifacts, merges realized/forecast price timelines, applies Helsinki release rules, exposes `SeriesPoint`, `PriceWindow`, and `DailyAverage` dataclasses plus price/wind payloads.
- `sensor.py`: sensor entities (upcoming + now price, daily averages, upcoming + now wind) keyed off coordinator data.
- `manifest.json`: minimal metadata (version, requirements, HA integration info).
- `tests/conftest.py`: injects project root into `sys.path` so tests can import `custom_components`.

## Coordinator Facts
- `_async_update_data`:
  - Resolves timezone via `ZoneInfo("Europe/Helsinki")`; raises `UpdateFailed` if tzdata missing.
  - Calculates `data_cutoff`: today midnight Helsinki time for showing all available data from beginning of today onwards.
  - Filters price and wind data ≥ `data_cutoff` to show aligned timelines.
  - Pulls Sähkötin CSV for the current Helsinki day and merges realized rows with forecast data from today onwards.
  - Current point found from merged series (latest point ≤ now). If no point exists at or before `now`, current is left unknown (no fallback to future).
  - Cheapest windows (3h/6h/12h) calculated across the merged series beginning at today’s Helsinki midnight (realized data followed by forecast points), preferring windows whose end is still ahead of `now`.
- Wind series filtered the same way as price (from today midnight).
- Cheapest rolling windows (3h/6h/12h) are derived from contiguous hourly points across full merged data and cached for sensor use.
- Full Helsinki days (00:00-23:00) are grouped into `DailyAverage` payloads for downstream sensors and UI.
- Custom cheapest window searches honour a user-defined lookahead horizon (hours ahead from the current hour anchor); candidate windows must end before the horizon expires.
- Networking via `aiohttp` session + `async_timeout`.

### Time semantics (important)
- "Now" means the latest sample at or before the current time, never a future value.
- "Next X" windows start strictly at the next full hour (T+1) and span X contiguous hours (e.g., next 3h = T+1..T+3). The current hour is excluded.
- When source data lacks a past/current sample, sensors must not present a future value as "now"; they should surface `unknown`/no state and include `raw_source` for transparency.

## Entity Contracts
- Price sensors:
  - `sensor.nordpool_predict_fi_price` → attributes `forecast`, `raw_source`.
  - `sensor.nordpool_predict_fi_price_now` → attributes `timestamp`, `raw_source`.
- `sensor.nordpool_predict_fi_price_daily_average` → attributes `daily_averages`, `daily_average_span_start`, `daily_average_span_end`, `raw_source`, `extra_fees`; state is the averaged price across every hour covered by the available full Helsinki days.
- `sensor.nordpool_predict_fi_price_next_1h` → attributes `timestamp`, `raw_source` (average over next starting hour: T+1).
- `sensor.nordpool_predict_fi_price_next_3h` → attributes `timestamp`, `raw_source` (average over next 3 hours: T+1 to T+3).
- `sensor.nordpool_predict_fi_price_next_6h` → attributes `timestamp`, `raw_source` (average over next 6 hours: T+1 to T+6).
- `sensor.nordpool_predict_fi_price_next_12h` → attributes `timestamp`, `raw_source` (average over next 12 hours: T+1 to T+12).
- Wind sensors:
  - `sensor.nordpool_predict_fi_windpower` → attributes `windpower_forecast`, `raw_source`.
  - `sensor.nordpool_predict_fi_windpower_now` → attributes `timestamp`, `raw_source`.
  - Naming is unified as `windpower` everywhere (not `wind_power`).
- Cheapest price window sensors (`sensor.nordpool_predict_fi_cheapest_{3|6|12}h_price_window`) expose lowest rolling averages across the Helsinki-today merged timeline (skipping windows that ended before `now`) along with `window_start`, `window_end`, `window_points`, and `raw_source` attributes. The matching `*_window_active` sensors flip to `True` while that window includes the present hour.
- The configurable cheapest window pair (`sensor.nordpool_predict_fi_cheapest_custom_price_window` and `_window_active`) uses the duration, hour mask, and lookahead horizon from four number entities (`number.nordpool_predict_fi_custom_window_{hours|start_hour|end_hour|lookahead_hours}`) and exposes the selected mask plus lookahead metadata in `custom_window_*` attributes.
 

## Configuration & Options
- Config flow (via `config_flow.py`) exposes base URL and update interval (1–720 minutes). Options flow mirrors the same schema.
- Default base URL: `https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy`.
- Update interval stored as `timedelta` in runtime config; options override entry data.

## Testing & Tooling
- `source .venv/bin/activate` to run pytest; we use `uv venv`
- Test suite: `pytest` with fixtures from `pytest-homeassistant-custom-component`.
- Lint: `ruff check`.
- Standard dev workflow (from repo root):
  ```bash
  source .venv/bin/activate  # local venv assumed
  python -m pytest
  ruff check
  ```
- Tests cover coordinator fetching/processing, config flows, sensors, binary sensors.

### Test intent (important)
- "Now" uses the latest point ≤ `now`; no future fallback.
- All "next X" sensors begin at T+1 and exclude the current hour.
- Boundary coverage includes the no-past-data case where current is `None`/`unknown`.
- Pytest config sets `asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml`.

## External Expectations
- Requires tzdata providing `Europe/Helsinki`; otherwise coordinator aborts with actionable error.
- Sähkötin CSV endpoint should be reachable; failures degrade to forecast-only data with warnings.
- Upstream JSON rows expected as `[timestamp_ms, value]`; coordinator skips malformed entries and sorts by timestamp.
- Forecast assumes 1-hour spacing; irregular intervals are ignored.
- Lovelace card snippets expect ApexCharts; update entity ids if users rename sensors.

## Common Tasks for Agents
- Adding platforms: update `const.PLATFORMS`, create `<platform>.py`, register entity classes using coordinator state.
- Modifying data fetch: adjust `_fetch_json` or `_safe_fetch_artifact`; ensure async + exception handling produce `UpdateFailed`.
- Extending attributes: edit sensor property methods; tests should assert attribute presence.
- Changing prediction logic: update coordinator calculations; keep tests in `tests/test_coordinator.py` aligned.
- Document UI changes in both `README.md` and `AGENTS.md`; reference card YAML when altering forecast attributes to avoid breaking dashboards.
- When requirements are unclear or you need Home Assistant conventions, use Context7: resolve the `home-assistant/core` library ID, pull focused docs with `context7__get-library-docs` (set `topic` if helpful), then apply the guidance—no guessing.

## Style
- Regions are sparse two-level only: top `#region setup|coordinator|sensor`; second `#region _update|_fetch|_parse|_time|_windows|_narration|_merge`; no third-level (`__...`), avoid micro-markers, goal is zoomed-out map clarity, omit endregion, ASCII only, comments before `from __future__` allowed.
- Versioning: CalVer `YYYY.MM.DD.N`; keep `custom_components/nordpool_predict_fi/manifest.json:version` and `pyproject.toml:version` identical; bump after user-visible changes once tests pass; egg-info mirrors on build.
- Comments: state intent and current facts only; no changelog-style A→B, no history or TODOs. Bad: `# Previously foobar broke so we changed it`; Good: `# Ensures sunroof forecast skips past hours`.
- Changelog: Common Changelog; daily-only (YYYY-MM-DD), no Unreleased; group by Added/Changed/Deprecated/Removed/Fixed/Security; concise user-focused bullets (consolidate commits, note breaking/migrations).
- Code style: PEP 8; explicit imports; clear, intent‑revealing names; small single‑purpose functions; Functional Core, Imperative Shell; typed public APIs; simplicity over cleverness.

## Cautions
- Do not block event loop; all I/O must be awaited.
- Maintain ascii (no unicode) unless file already contains it.
- Respect Home Assistant conventions (entity unique IDs, device info).
- Never reset user-modified git state; worktree may be dirty.
- Never perform git operations unless explicitly requested by the user.
- When adding tests, rely on helper classes (`MockConfigEntry`, `enable_custom_integrations`) already present.
