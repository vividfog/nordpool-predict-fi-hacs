# Nordpool Predict FI – Agent Handbook

source .venv/bin/activate

## Snapshot
- Custom Home Assistant integration; core code under `custom_components/nordpool_predict_fi/`.
- Python 3.12 target; asynchronous I/O via Home Assistant helpers.
- External data: hourly price forecasts from `prediction.json`, optional `windpower.json`.
- Integration platforms: `sensor`.
- Sample Lovelace cards in repo root (ApexCharts) for price + wind.

## Primary Modules
- `__init__.py`: sets up `DataUpdateCoordinator`, registers platforms, normalises config entry options.
- `const.py`: domain constants, default config, attribute keys.
- `coordinator.py`: fetches JSON artifacts, filters price data to Helsinki release rules, exposes `SeriesPoint` and `PriceWindow` dataclasses plus price/wind payloads.
- `sensor.py`: sensor entities (upcoming price and optional upcoming wind) keyed off coordinator data.
- `manifest.json`: minimal metadata (version, requirements, HA integration info).
- `tests/conftest.py`: injects project root into `sys.path` so tests can import `custom_components`.

## Coordinator Facts
- `_async_update_data`:
  - Resolves timezone via `ZoneInfo("Europe/Helsinki")`; raises `UpdateFailed` if tzdata missing.
  - Uses Helsinki local time to decide prediction start: before 14:00 → tomorrow 01:00; after → day after tomorrow 01:00 (both local). All timestamps stored UTC.
  - Filters price series ≥ cutoff and retains a reference to the next effective timestamp.
- Wind optional toggled by config flag.
- Cheapest rolling windows (3h/6h/12h) are derived from contiguous hourly points and cached for sensor use.
- Networking via `aiohttp` session + `async_timeout`.

## Entity Contracts
- Price sensor (entity id defaults to `sensor.nordpool_predict_fi_upcoming_price`) attributes: `forecast`, `next_valid_from`, `raw_source`.
- Wind sensor (entity id defaults to `sensor.nordpool_predict_fi_upcoming_wind_power`) attributes: `windpower_forecast`, `next_valid_from`, `raw_source`.
- Cheapest price window sensors (`sensor.nordpool_predict_fi_cheapest_3h_price_window`, `..._6h_...`, `..._12h_...`) expose the lowest rolling averages along with `window_start`, `window_end`, `window_points`, and `raw_source` attributes.

## Configuration & Options
- Config flow (via `config_flow.py`) exposes base URL, update interval (1–720 minutes), optional feeds. Options flow mirrors same schema.
- Default base URL: `https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy`.
- Update interval stored as `timedelta` in runtime config; options override entry data.

## Testing & Tooling
- Test suite: `pytest` with fixtures from `pytest-homeassistant-custom-component`.
- Lint: `ruff check`.
- Standard dev workflow (from repo root):
  ```bash
  source .venv/bin/activate  # local venv assumed
  python -m pytest
  ruff check
  ```
- Tests cover coordinator fetching/processing, config flows, sensors, binary sensors.

## External Expectations
- Requires tzdata providing `Europe/Helsinki`; otherwise coordinator aborts with actionable error.
- Upstream JSON rows expected as `[timestamp_ms, value]`; coordinator skips malformed entries and sorts by timestamp.
- Forecast assumes 1-hour spacing; irregular intervals are ignored.
- Lovelace card snippets expect ApexCharts; update entity ids if users rename sensors.

## Common Tasks for Agents
- Adding platforms: update `const.PLATFORMS`, create `<platform>.py`, register entity classes using coordinator state.
- Modifying data fetch: adjust `_fetch_json` or `_safe_fetch_optional`; ensure async + exception handling produce `UpdateFailed`.
- Extending attributes: edit sensor property methods; tests should assert attribute presence.
- Changing prediction logic: update coordinator calculations; keep tests in `tests/test_coordinator.py` aligned.
- Document UI changes in both `README.md` and `AGENTS.md`; reference card YAML when altering forecast attributes to avoid breaking dashboards.

## Cautions
- Do not block event loop; all I/O must be awaited.
- Maintain ascii (no unicode) unless file already contains it.
- Never reset user-modified git state; worktree may be dirty.
- Respect Home Assistant conventions (entity unique IDs, device info).
- When adding tests, rely on helper classes (`MockConfigEntry`, `enable_custom_integrations`) already present.
