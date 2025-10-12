# Nordpool Predict FI – Home Assistant Integration

Nordpool Predict FI is a Home Assistant integration that mirrors the forecasts published by [`vividfog/nordpool-predict-fi`](https://github.com/vividfog/nordpool-predict-fi). It reads the hourly price feed (`prediction.json`) and, if enabled, the wind forecast (`windpower.json`), then exposes the data as sensors.

Nordpool posts the next day’s Finnish spot prices at 14:00 Helsinki time. Until that happens the integration only shows yet-to-come hours: before 14:00 you see tomorrow from 01:00 onward, and after 14:00 the view jumps to the day after tomorrow. The wind forecast is trimmed the same way so both series stay aligned.

The sample YAML cards ship with Nordpool’s realised prices from `sensor.nordpool_kwh_fi_eur_3_10_0255`; change the sensor ID to match your setup.

---

## What You Get

| Entity | Type | Description |
| --- | --- | --- |
| `sensor.nordpool_predict_fi_upcoming_price` | Sensor | Continuous hourly price timeline (`c/kWh`) built from Sähkötin realizations + Nordpool Predict forecasts, with `next_valid_from` for the next market update. |
| `sensor.nordpool_predict_fi_price_now` | Sensor | Latest price value at or before the current hour, plus the timestamp it originated from. |
| `sensor.nordpool_predict_fi_upcoming_wind_power` | Optional sensor | Upcoming wind production forecast (MW) with the forecast series and `next_valid_from` attribute. |
| `sensor.nordpool_predict_fi_windpower_now` | Optional sensor | Wind power value for the next hour (same as `current` in the feed) with its timestamp. |
| `sensor.nordpool_predict_fi_cheapest_3h_price_window` | Sensor | Lowest average of any 3-hour window ahead; attributes expose `window_start`, `window_end`, `window_points`, and `raw_source`. |
| `sensor.nordpool_predict_fi_cheapest_6h_price_window` | Sensor | Same as above for 6-hour windows, useful for longer running appliances. |
| `sensor.nordpool_predict_fi_cheapest_12h_price_window` | Sensor | Tracks the cheapest 12-hour block for day-level planning. |
| `sensor.nordpool_predict_fi_narration_fi` | Sensor | Finnish narration summary/ingress as the sensor state; the full Markdown lives in `content` with `source_url` pointing at the raw file. |
| `sensor.nordpool_predict_fi_narration_en` | Sensor | English narration equivalent with the same attributes for dashboards or automations. |

All timestamps are UTC ISO8601 strings; Home Assistant handles local conversion based on your instance settings.

Price data is provided courtesy of [Sähkötin](https://sahkotin.fi/hours).

### Showing the narration

Use a Markdown card to render the full narration; the example below pulls the Finnish text and falls back to English if it is missing:

```yaml
type: markdown
content: |
  {{ state_attr('sensor.nordpool_predict_fi_narration_fi', 'content')
     or state_attr('sensor.nordpool_predict_fi_narration_en', 'content') }}
```

Both narration sensors expose `language`, `summary`, `content`, and `source_url` attributes so you can automate announcements, notifications, or alternative Lovelace cards.

---

## Installation (HACS)

1. Open HACS → Integrations → *Custom repositories* → add `https://github.com/vividfog/nordpool-predict-fi-hacs` (`Integration` category).
2. Install **Nordpool Predict FI** from HACS and restart Home Assistant.

---

## Configuration Flow

`Settings → Devices & Services → Add Integration → Nordpool Predict FI`

During setup (or later via *Configure*) you can tweak:

- **Base URL** – defaults to `https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy`. Point it to another host if you mirror the files.
- **Update interval** – polling frequency in minutes (1–720, default 30).
- **Load wind power data** – toggles downloads of `windpower.json` and enables the wind sensor.

The host needs tzdata with the `Europe/Helsinki` zone. If that package is missing the coordinator raises a clear error in the Home Assistant logs.

---

## Working With the Data

- Forecast rows are treated as hourly points sorted by time.
- Sähkötin CSV data for the current Helsinki day is merged with Nordpool Predict forecasts, so the `forecast` attribute already contains realized + predicted prices in one timeline.
- Model-only features (cheapest windows, `next_valid_from`) still respect the 14:00 Nordpool market release.
- Rolling cheapest windows (3h, 6h, 12h) are calculated in the coordinator and exposed both as sensor states (average price) and attributes for automations.

## Data Sources

- Hourly realized prices: [Sähkötin](https://sahkotin.fi/hours)
- Forecast artifacts: [`prediction.json`](https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy/prediction.json), optional [`windpower.json`](https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy/windpower.json)

## Dashboard Cards

Copy the ready-made ApexCharts cards from the repository root:

![Screenshot of forecast vs. market price card in ApexCharts](docs/npf_card_price.png)

- [`npf_card_price.yaml`](npf_card_price.yaml) – combines the price sensor forecast with wind power to highlight how production correlates with price. Requires both `sensor.nordpool_predict_fi_upcoming_price` and `sensor.nordpool_predict_fi_upcoming_wind_power`.
- [`npf_card_wind.yaml`](npf_card_wind.yaml) – focuses on wind output with price as supporting data over a week.

![Screenshot of combined price and wind power card in ApexCharts](docs/npf_card_wind.png)

Paste the YAML into the Raw Configuration Editor of a Lovelace dashboard that has [ApexCharts Card](https://github.com/RomRider/apexcharts-card) installed. Update the entity IDs if your sensors use different names. The cards read the forecast attributes exported by the price and wind sensors.

---

## Troubleshooting

- **No data after install** – verify the Base URL is reachable and serves the JSON files (use your browser or `curl`). Check Supervisor logs for `UpdateFailed` messages.
- **Timestamps look wrong** – the integration reports UTC; Home Assistant handles most conversions but ensure your system time zone is configured correctly.
- **Missing tzdata** – on minimal containers install a tzdata package (`apk add tzdata`, `apt install tzdata`, etc.).

---

## Development

- Python 3.12+ is required.
- Install dev tooling and dependencies:
  ```bash
  uv venv --python 3.12 --seed
  source .venv/bin/activate
  pip install -r requirements-dev.txt
  ```
- Run linters and tests:
  ```bash
  ruff check
  pytest
  ```
- Coordinator tests mock network I/O; sensor tests validate entity wiring. Add tests alongside any new behaviour.
- `scripts/dev_fetch.py` is a helper that downloads the JSON artifacts for local debugging (no Home Assistant required).

The integration follows Home Assistant async patterns. Avoid blocking calls, keep changes in ASCII, and ensure new features are represented in both documentation and tests.
