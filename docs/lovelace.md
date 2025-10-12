# Lovelace examples

The integration exposes a continuous price timeline (realized + forecast) and a wind power forecast. The examples below use the [ApexCharts card](https://github.com/RomRider/apexcharts-card) and mirror the ready‑to‑use YAML stored in this repository.

## Price & wind overview

Paste the snippet into the Lovelace *Manual card editor* or reference `docs/npf_card_price.yaml` directly.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Sähkön hinta ja tuulivoima
  show_states: true
  colorize_states: true
  standard_format: true
  disable_actions: true
graph_span: 7d
experimental:
  color_threshold: true
span:
  start: hour
now:
  show: true
  color: "#1c88fb"
  label: Nyt
series:
  - entity: sensor.nordpool_predict_fi_price
    name: Sähkön hinta
    type: line
    yaxis_id: price
    extend_to: now
    curve: stepline
    stroke_width: 1.5
    float_precision: 2
    color: limegreen
    opacity: 1
    color_threshold:
      - value: 5
        color: lime
        opacity: 1
      - value: 10
        color: limegreen
        opacity: 1
      - value: 15
        color: gold
        opacity: 1
      - value: 20
        color: darkorange
        opacity: 1
      - value: 30
        color: red
        opacity: 1
      - value: 999
        color: darkred
        opacity: 1
    data_generator: |
      const data = entity.attributes.forecast || [];
      return data.map((item) => [item.timestamp, item.value]);
    show:
      in_chart: true
      in_header: false
      in_legend: true
      legend_value: false
  - entity: sensor.nordpool_predict_fi_price
    type: area
    yaxis_id: price
    extend_to: now
    curve: stepline
    stroke_width: 0
    float_precision: 1
    color: limegreen
    opacity: 0.16
    data_generator: |
      const data = entity.attributes.forecast || [];
      return data.map((item) => [item.timestamp, item.value]);
    show:
      in_chart: true
      in_header: false
      in_legend: false
      legend_value: false
  - entity: sensor.nordpool_predict_fi_wind_power
    name: Tuulivoima
    type: column
    yaxis_id: wind
    float_precision: 0
    color: skyblue
    opacity: 0.1
    extend_to: now
    stroke_width: 0
    curve: stepline
    data_generator: |
      const data = entity.attributes.windpower_forecast || [];
      return data.map((item) => [item.timestamp, item.value / 1000]);
    show:
      in_chart: true
      in_header: false
      in_legend: true
      legend_value: false
  - entity: sensor.nordpool_predict_fi_price_now
    name: Hinta nyt
    unit: ¢
    float_precision: 1
    color: dimgray
    show:
      in_chart: false
      legend_value: false
      in_header: raw
      header_color_threshold: true
    color_threshold:
      - value: 5
        color: lime
        opacity: 1
      - value: 10
        color: limegreen
        opacity: 1
      - value: 15
        color: gold
        opacity: 1
      - value: 20
        color: darkorange
        opacity: 1
      - value: 30
        color: red
        opacity: 1
      - value: 999
        color: darkred
        opacity: 1
  - entity: sensor.nordpool_predict_fi_price_next_6h
    name: Seuraavat 6h
    unit: ¢
    float_precision: 1
    color: dimgray
    color_threshold:
      - value: 5
        color: lime
        opacity: 1
      - value: 10
        color: limegreen
        opacity: 1
      - value: 15
        color: gold
        opacity: 1
      - value: 20
        color: darkorange
        opacity: 1
      - value: 30
        color: red
        opacity: 1
      - value: 999
        color: darkred
        opacity: 1
    show:
      in_chart: false
      legend_value: false
      header_color_threshold: true
  - entity: sensor.nordpool_predict_fi_cheapest_6h_price_window
    name: Halvin 6h
    unit: ¢
    float_precision: 1
    color: dimgray
    color_threshold:
      - value: 5
        color: lime
        opacity: 1
      - value: 10
        color: limegreen
        opacity: 1
      - value: 15
        color: gold
        opacity: 1
      - value: 20
        color: darkorange
        opacity: 1
      - value: 30
        color: red
        opacity: 1
      - value: 999
        color: darkred
        opacity: 1
    show:
      in_chart: false
      legend_value: false
      header_color_threshold: true
  - entity: sensor.nordpool_predict_fi_wind_power
    name: Tuulivoima
    float_precision: 0
    color: skyblue
    show:
      in_chart: false
      in_header: true
      in_legend: true
      legend_value: false
yaxis:
  - id: price
    decimals: 0
    apex_config:
      tickAmount: 4
      forceNiceScale: true
      title:
        text: Hinta (¢/kWh)
  - id: wind
    opposite: true
    decimals: 0
    apex_config:
      tickAmount: 4
      forceNiceScale: true
      title:
        text: Tuulivoima (GW)
apex_config:
  chart:
    height: 384
    toolbar:
      show: false
  grid:
    strokeDashArray: 3
  legend:
    show: false
    customLegendItems:
      - Sähkön hinta (¢/kWh)
      - Tuulivoima (GW)
  xaxis:
    type: datetime
    labels:
      formatter: |
        EVAL:function (value, timestamp) {
          const ts = timestamp || value;
          const date = new Date(ts);
          if (Number.isNaN(date.getTime())) {
            return value;
          }
          const days = ['su', 'ma', 'ti', 'ke', 'to', 'pe', 'la'];
          return days[date.getDay()];
        }
  tooltip:
    enabled: false
  markers:
    size: 0

```

## Wind production focus

The wind-first variant keeps the same styling but uses the wind forecast as the primary series. Copy it from `docs/npf_card_wind.yaml`.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Tuulivoima- ja hintaennuste
  show_states: true
  colorize_states: true
  standard_format: true
  disable_actions: true
graph_span: 7d
experimental:
  color_threshold: true
span:
  start: hour
now:
  show: true
  color: "#1c88fb"
  label: Nyt
series:
  - entity: sensor.nordpool_predict_fi_wind_power
    name: Tuulivoima
    type: line
    yaxis_id: wind
    extend_to: now
    curve: stepline
    stroke_width: 1.5
    float_precision: 2
    color: skyblue
    opacity: 1
    color_threshold:
      - value: 1
        color: red
      - value: 2
        color: skyblue
      - value: 3
        color: deepskyblue
      - value: 4
        color: dodgerblue
      - value: 5
        color: blue
      - value: 6
        color: mediumblue
      - value: 7
        color: darkblue
      - value: 99
        color: midnightblue
    data_generator: |
      const data = entity.attributes.windpower_forecast || [];
      return data.map((item) => [item.timestamp, item.value / 1000]);
    show:
      in_legend: true
      legend_value: false
      in_header: false
  - entity: sensor.nordpool_predict_fi_price
    name: Hinta nyt
    type: column
    yaxis_id: price
    float_precision: 1
    color: dimgray
    opacity: 0.33
    extend_to: now
    stroke_width: 0
    data_generator: |
      const data = entity.attributes.forecast || [];
      return data.map((item) => [item.timestamp, item.value]);
    show:
      in_legend: true
      legend_value: false
      in_header: false
  - entity: sensor.nordpool_predict_fi_wind_power
    type: area
    yaxis_id: wind
    extend_to: now
    curve: stepline
    stroke_width: 0
    float_precision: 1
    color: dodgerblue
    opacity: 0.16
    data_generator: |
      const data = entity.attributes.windpower_forecast || [];
      return data.map((item) => [item.timestamp, item.value / 1000]);
    show:
      in_chart: true
      in_header: false
      in_legend: false
      legend_value: false
  - entity: sensor.nordpool_predict_fi_wind_power
    name: Tuulivoima nyt
    float_precision: 0
    color: skyblue
    color_threshold:
      - value: 1000
        color: red
      - value: 2000
        color: skyblue
      - value: 3000
        color: deepskyblue
      - value: 4000
        color: dodgerblue
      - value: 5000
        color: blue
      - value: 6000
        color: mediumblue
      - value: 7000
        color: darkblue
      - value: 8000
        color: midnightblue
    show:
      in_chart: false
      in_header: true
      in_legend: false
      legend_value: false
  - entity: sensor.nordpool_predict_fi_price_now
    name: Hinta nyt
    unit: ¢
    float_precision: 1
    color: dimgray
    color_threshold:
      - value: 5
        color: lime
        opacity: 1
      - value: 10
        color: limegreen
        opacity: 1
      - value: 15
        color: gold
        opacity: 1
      - value: 20
        color: darkorange
        opacity: 1
      - value: 30
        color: red
        opacity: 1
      - value: 999
        color: darkred
        opacity: 1
    show:
      in_chart: false
      legend_value: false
      in_header: raw
      header_color_threshold: true
  - entity: sensor.nordpool_predict_fi_price_next_6h
    float_precision: 1
    color: dimgray
    unit: ¢
    name: Seuraavat 6h
    color_threshold:
      - value: 5
        color: lime
        opacity: 1
      - value: 10
        color: limegreen
        opacity: 1
      - value: 15
        color: gold
        opacity: 1
      - value: 20
        color: darkorange
        opacity: 1
      - value: 30
        color: red
        opacity: 1
      - value: 999
        color: darkred
        opacity: 1
    show:
      in_chart: false
      legend_value: false
      header_color_threshold: true
  - entity: sensor.nordpool_predict_fi_cheapest_6h_price_window
    color: dimgray
    float_precision: 1
    unit: ¢
    name: Halvin 6h
    color_threshold:
      - value: 5
        color: lime
        opacity: 1
      - value: 10
        color: limegreen
        opacity: 1
      - value: 15
        color: gold
        opacity: 1
      - value: 20
        color: darkorange
        opacity: 1
      - value: 30
        color: red
        opacity: 1
      - value: 999
        color: darkred
        opacity: 1
    show:
      in_chart: false
      legend_value: false
      header_color_threshold: true
yaxis:
  - id: wind
    min: 0
    decimals: 0
    apex_config:
      forceNiceScale: true
      tickAmount: 4
      title:
        text: Tuulivoima (GW)
  - id: price
    opposite: true
    decimals: 0
    apex_config:
      tickAmount: 4
      forceNiceScale: true
      title:
        text: Hinta (¢/kWh)
apex_config:
  chart:
    height: 384
    toolbar:
      show: false
  grid:
    strokeDashArray: 3
  legend:
    show: false
    customLegendItems:
      - Tuulivoima (GW)
      - Ennustettu hinta (¢/kWh)
  xaxis:
    type: datetime
    labels:
      formatter: |
        EVAL:function (value, timestamp) {
          const ts = timestamp || value;
          const date = new Date(ts);
          if (Number.isNaN(date.getTime())) {
            return value;
          }
          const days = ['su', 'ma', 'ti', 'ke', 'to', 'pe', 'la'];
          return days[date.getDay()];
        }
  tooltip:
    enabled: false
  markers:
    size: 0
```
