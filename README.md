# Nordpool Predict FI – Home Assistant Integration

**Nordpool Predict FI is a Home Assistant integration that displays the forecasts published by [`vividfog/nordpool-predict-fi`](https://github.com/vividfog/nordpool-predict-fi). It reads the hourly price feed (`prediction.json`) and the wind forecast (`windpower.json`), then exposes the data as sensors.**

The integration shows all available data from today (Helsinki time) onwards. Price data combines [Sähkötin](https://sahkotin.fi/hours) realized prices with forecast data, transitioning from actual to predicted values. Wind power data is shown similarly.

Cheapest windows work across the entire data timeline, using both realized and forecast data to find the most economical future price windows throughout the week.

---

## Sensors

| Entity | Type | Description |
| --- | --- | --- |
| `sensor.nordpool_predict_fi_price` | Sensor | Continuous hourly price timeline (`c/kWh`) built from Sähkötin realizations + Nordpool Predict forecasts. |
| `sensor.nordpool_predict_fi_price_now` | Sensor | Latest price value at or before the current hour, plus the timestamp it originated from. |
| `sensor.nordpool_predict_fi_price_next_1h` | Sensor | Average price for the next starting 1 hour. |
| `sensor.nordpool_predict_fi_price_next_3h` | Sensor | Average price for the next 3 hours. |
| `sensor.nordpool_predict_fi_price_next_6h` | Sensor | Average price for the next 6 hours. |
| `sensor.nordpool_predict_fi_price_next_12h` | Sensor | Average price for the next 12 hours. |
| `number.nordpool_predict_fi_extra_fees` | Number | Adjustable surcharge (c/kWh) that is added to every price reading; defaults to 0.0. |
| `sensor.nordpool_predict_fi_windpower` | Optional sensor | Wind production forecast (MW) with the complete forecast series. |
| `sensor.nordpool_predict_fi_windpower_now` | Optional sensor | Wind power value for the current hour with its timestamp. |
| `sensor.nordpool_predict_fi_cheapest_3h_price_window` | Sensor | Lowest average of any 3-hour window in the data; attributes expose `window_start`, `window_end`, `window_points`, and `raw_source`. |
| `sensor.nordpool_predict_fi_cheapest_6h_price_window` | Sensor | Same as above for 6-hour windows, useful for longer running appliances. |
| `sensor.nordpool_predict_fi_cheapest_12h_price_window` | Sensor | Tracks the cheapest 12-hour block for day-level planning. |
| `sensor.nordpool_predict_fi_narration_fi` | Sensor | Finnish narration summary/ingress as the sensor state; the full Markdown lives in `content` with `source_url` pointing at the raw file. |
| `sensor.nordpool_predict_fi_narration_en` | Sensor | English narration equivalent with the same attributes for dashboards or automations. |

All timestamps are UTC ISO8601 strings; Home Assistant handles local conversion based on your instance settings.

Narration sensors expose `language`, `summary` (state), `content` (full Markdown), and `source_url` attributes.

---

## Installation (HACS)

1. Open HACS → Integrations → *Custom repositories* → add:
  - `https://github.com/vividfog/nordpool-predict-fi-hacs`
  - `Integration` category
2. Install **Nordpool Predict FI** from HACS and restart Home Assistant.

---

## Configuration Flow

`Settings → Devices & Services → Add Integration → Nordpool Predict FI`

During setup (or later via *Configure*) you can tweak:

- **Base URL** – defaults to `https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy`. Point it to another host if you mirror the files.
- **Update interval** – polling frequency in minutes (1–720, default 30).

The host needs tzdata with the `Europe/Helsinki` zone. If that package is missing the coordinator raises an error in the Home Assistant logs.

---

## Working With the Data

- All data (price forecasts, wind power, and realized prices) is shown from beginning of today (Helsinki time) onwards.
- The dedicated extra fees number lets you overlay grid fees or markups in cents per kWh; the value is reflected in price sensor states, cheapest windows, and their `extra_fees` attributes.
- Sähkötin CSV data for the current Helsinki day is merged with Nordpool Predict FI forecasts, so the `forecast` attribute already contains realized + predicted prices in one timeline.
- The price sensor also exposes `forecast_start`, the first forecast hour after realized data, so dashboards can mark where predictions kick in.
- Cheapest windows (3h, 6h, 12h) work across the entire available data, using both realized and forecast prices to find the most economical periods throughout the week.
- All cheapest window calculations are done in the coordinator and exposed both as sensor states (average price) and attributes for automations.

## Data Sources

- Hourly realized prices: [Sähkötin](https://sahkotin.fi/hours)
- Forecast artifacts: [`prediction.json`](https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy/prediction.json) and [`windpower.json`](https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy/windpower.json)

## Dashboard Cards

Manual card snippets live in docs — see [`docs/README.md`](docs/README.md) for copy/paste steps. Install [ApexCharts Card](https://github.com/RomRider/apexcharts-card) (and Button Card for the table) before adding them to your dashboard.

### Price vs. Wind Outlook

[`npf_card_price.yaml`](docs/npf_card_price.yaml) combines realized + forecast prices with wind production so you can spot when generation pulls prices down.

![ApexCharts price card showing realized prices, forecast, and wind overlay](docs/npf_card_price.jpeg)

### Wind Production Spotlight

[`npf_card_wind.yaml`](docs/npf_card_wind.yaml) flips the perspective to wind-first while keeping the price trace available for context across the week.

![ApexCharts wind card showing wind power focus with price overlay](docs/npf_card_wind.png)

### Cheapest Window Countdown

[`npf_card_cheapest_countdown.yaml`](docs/npf_card_cheapest_countdown.yaml) presents the best 3 h, 6 h, and 12 h windows side by side, using Button Card to keep the layout compact.

![Button Card table comparing cheapest 3h, 6h, and 12h price windows](docs/npf_card_cheapest_countdown.png)

### Morning Briefing Summary

[`npf_card_summary_fi.yaml`](docs/npf_card_summary_fi.yaml) and [`npf_card_summary_en.yaml`](docs/npf_card_summary_en.yaml) surface the short-form narrations; pair them with the full Markdown versions (`npf_card_narration_fi.yaml`, `npf_card_narration_en.yaml`) for longer notes.

![Button Card showing the Finnish daily summary with price highlights](docs/npf_card_summary_fi.jpeg)

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
- The integration follows Home Assistant async patterns. Avoid blocking calls, keep changes in ASCII, and ensure new features are represented in both documentation and tests.
- `AGENTS.md` is provided for AI-assisted development.
