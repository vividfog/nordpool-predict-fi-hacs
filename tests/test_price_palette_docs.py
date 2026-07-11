from pathlib import Path
import re


DOCS = Path(__file__).parents[1] / "docs"


def test_apex_price_thresholds_use_darker_green_for_cheaper_band() -> None:
    expected_counts = {
        "npf_card_price.yaml": 4,
        "npf_card_wind.yaml": 3,
    }

    for filename, expected_count in expected_counts.items():
        content = (DOCS / filename).read_text(encoding="utf-8")
        dark_cheap_bands = re.findall(
            r"- value: (?:3|5)\n"
            r"\s+color: limegreen\n"
            r"\s+opacity: 1\n"
            r"\s+- value: (?:6|10)\n"
            r"\s+color: lime",
            content,
        )

        assert len(dark_cheap_bands) == expected_count


def test_apex_price_legend_and_area_use_cheapest_band_color() -> None:
    content = (DOCS / "npf_card_price.yaml").read_text(encoding="utf-8")

    assert re.search(
        r"name: Sähkön hinta\n(?:.*\n){6}\s+color: limegreen\n",
        content,
    )
    assert re.search(
        r"type: area\n(?:.*\n){5}\s+color: limegreen\n",
        content,
    )


def test_plotly_calendar_uses_darker_green_for_cheapest_band() -> None:
    content = (DOCS / "npf_card_price_calendar_plotly.yaml").read_text(
        encoding="utf-8"
    )

    assert "{ min: -Infinity, max: 5, color: 'limegreen' }" in content
    assert "{ min: 5, max: 10, color: 'lime' }" in content


def test_generated_wind_series_keep_a_visible_stroke() -> None:
    expected_series = {
        "npf_card_price.yaml": "type: column",
        "npf_card_wind.yaml": "type: area",
    }

    for filename, series_type in expected_series.items():
        content = (DOCS / filename).read_text(encoding="utf-8")
        assert re.search(
            rf"entity: sensor\.nordpool_predict_fi_windpower\n"
            rf"(?:.*\n){{0,3}}\s+{series_type}\n"
            rf"(?:.*\n){{0,6}}\s+stroke_width: 0\.1\n",
            content,
        )
