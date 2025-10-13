# Lovelace Cards (Copy/Paste)

These are ready-to-use Lovelace card snippets for the Nordpool Predict FI integration. Use them by copying the YAML into a Manual card in your dashboard.

Requirements
- Install ApexCharts Card via HACS (Frontend → ApexCharts Card).
- Install this integration and ensure entities exist (see README table in the repo root).

How to use
1) In Home Assistant, open your dashboard → Edit → Add Card → Manual.
2) Open one of these files and copy its contents:
   - npf_card_price.yaml — price-first card with wind overlay.
   - npf_card_wind.yaml — wind-first card with price overlay.
   - npf_card_narration_fi.yaml — full Finnish narration (Markdown content).
   - npf_card_narration_en.yaml — full English narration (Markdown content).
   - npf_card_summary_fi.yaml — short Finnish summary (sensor state).
   - npf_card_summary_en.yaml — short English summary (sensor state).
3) Paste into the Manual card and save. If you have renamed entities, adjust the entity IDs in the YAML.

Notes
- The wind series is in MW; examples divide by 1000 to show GW.
- Price series is in c/kWh and includes realized + forecast in one timeline.
- Next/cheapest sensors are optional in the headers; remove lines if you don’t use them.
 - Narration sensors: the state is the short summary; the full article is in the `content` attribute with a `source_url` attribute pointing to the origin.

Troubleshooting
- If a chart is empty, verify the entity IDs in the YAML match your system (Developer Tools → States).
- Ensure ApexCharts Card is installed and available in your frontend.
