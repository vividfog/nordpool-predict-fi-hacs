# Lovelace Cards & Automation Templates

These are ready-to-use Lovelace card snippets plus a polling automation example for the Nordpool Predict FI integration. Use the card YAML in Manual dashboard cards, and drop the automation into YAML mode within Settings → Automations & Scenes.

## Requirements
- Install ApexCharts Card via HACS (Frontend → ApexCharts Card).
- Install Button Card by @RomRider via HACS (Frontend → Button Card) for the countdown table.
- Install this integration and ensure entities exist (see README overview in the repo root).

## How to use

1) In Home Assistant, open your dashboard → Edit → Add Card → Manual.
2) Open one of these files and copy its contents:
   - `npf_card_cheapest_countdown.yaml` — compact table comparing all cheapest time windows.
   - `npf_card_daily_averages_md.yaml` — markdown card listing each Helsinki day with average, min, and max prices.
   - `npf_card_daily_averages_button-card.yaml` — button-card table with weekday labels and daily min/avg/max columns.
   - `npf_card_price.yaml` — price-first card with wind overlay.
   - `npf_card_wind.yaml` — wind-first card with price overlay.
   - `npf_card_narration_fi.yaml` — full Finnish narration (Markdown content).
   - `npf_card_narration_en.yaml` — full English narration (Markdown content).
   - `npf_card_summary_fi.yaml` — short Finnish summary (sensor state).
   - `npf_card_summary_en.yaml` — short English summary (sensor state).
   - `automation_cheapest_6h.yaml` — automation template that pings every 10 minutes and reacts once the cheapest 6-hour window is active.

3) Paste into the Manual card and save. If you have renamed entities, adjust the entity IDs in the YAML.

### Automation example

1) `Settings → Automations & Scenes → Automations → Create Automation → Start with empty automation`.
2) Switch to YAML mode (three-dot menu → *Edit in YAML*).
3) Replace the content with `automation_cheapest_6h.yaml`.
4) Adjust the numeric price threshold and action to suit your EV charger.

## Troubleshooting

- If a chart is empty, verify the entity IDs in the YAML match your system (Developer Tools → States).
- Ensure ApexCharts Card and Button Card are installed and available in your frontend.
