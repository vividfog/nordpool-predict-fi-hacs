# Lovelace Cards (Copy/Paste)

These are ready-to-use Lovelace card snippets for the Nordpool Predict FI integration. Use them by copying the YAML into a Manual card in your dashboard.

## Requirements
- Install ApexCharts Card via HACS (Frontend → ApexCharts Card).
- Install Button Card by @RomRider via HACS (Frontend → Button Card) for the countdown table.
- Install this integration and ensure entities exist (see README overview in the repo root).

## How to use

1) In Home Assistant, open your dashboard → Edit → Add Card → Manual.
2) Open one of these files and copy its contents:
   - `npf_card_cheapest_countdown.yaml` — compact table comparing all cheapest time windows.
   - `npf_card_daily_averages.yaml` — markdown card that lists each Helsinki day with its average price.
   - `npf_card_price.yaml` — price-first card with wind overlay.
   - `npf_card_wind.yaml` — wind-first card with price overlay.
   - `npf_card_narration_fi.yaml` — full Finnish narration (Markdown content).
   - `npf_card_narration_en.yaml` — full English narration (Markdown content).
   - `npf_card_summary_fi.yaml` — short Finnish summary (sensor state).
   - `npf_card_summary_en.yaml` — short English summary (sensor state).

3) Paste into the Manual card and save. If you have renamed entities, adjust the entity IDs in the YAML.

## Troubleshooting

- If a chart is empty, verify the entity IDs in the YAML match your system (Developer Tools → States).
- Ensure ApexCharts Card and Button Card are installed and available in your frontend.
