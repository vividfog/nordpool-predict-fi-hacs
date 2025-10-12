#!/usr/bin/env python3
"""Fetch Nordpool Predict FI artifacts for quick validation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    from custom_components.nordpool_predict_fi.const import DEFAULT_BASE_URL
except Exception:  # pragma: no cover - script still works without HA deps
    DEFAULT_BASE_URL = "https://raw.githubusercontent.com/vividfog/nordpool-predict-fi/main/deploy"

ARTIFACTS = (
    "prediction.json",
    "windpower.json",
)


def _is_http(base: str) -> bool:
    return base.startswith("http://") or base.startswith("https://")


def _load_json_from_http(url: str, timeout: float) -> Any:
    req = request.Request(url, headers={"User-Agent": "nordpool-predict-fi-dev-fetch/0.1"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
    except error.HTTPError as err:  # pragma: no cover - passthrough for CLI feedback
        raise RuntimeError(f"HTTP error {err.code} for {url}") from err
    except error.URLError as err:
        raise RuntimeError(f"Network error fetching {url}: {err.reason}") from err

    try:
        text = raw.decode(resp.headers.get_content_charset() or "utf-8")
    except Exception:
        text = raw.decode("utf-8", errors="replace")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as err:
        snippet = text[:120].replace("\n", " ")
        raise RuntimeError(f"Non-JSON response from {url}: {err} (snippet: {snippet!r})") from err

    lower_type = content_type.lower()
    if lower_type and all(kind not in lower_type for kind in ("json", "text/plain")):
        raise RuntimeError(f"Unexpected content-type {content_type!r} from {url}")

    return payload


def _load_json_from_path(base_path: Path, filename: str) -> Any:
    path = base_path / filename
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        snippet = text[:120].replace("\n", " ")
        raise RuntimeError(f"Non-JSON content in {path}: {err} (snippet: {snippet!r})") from err


def load_artifact(base: str, filename: str, timeout: float) -> Any:
    if _is_http(base):
        url = f"{base.rstrip('/')}/{filename}"
        return _load_json_from_http(url, timeout)
    base_path = Path(base).expanduser().resolve()
    return _load_json_from_path(base_path, filename)


def describe_series(rows: Any) -> tuple[int, datetime | None, datetime | None]:
    points = 0
    first: datetime | None = None
    last: datetime | None = None
    if not isinstance(rows, list):
        return points, first, last
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        timestamp = _safe_datetime(row[0])
        if timestamp is None:
            continue
        points += 1
        if first is None or timestamp < first:
            first = timestamp
        if last is None or timestamp > last:
            last = timestamp
    return points, first, last


def _safe_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    except Exception:
        return None


def format_dt(value: datetime | None) -> str:
    return value.isoformat() if value else "n/a"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="HTTP(S) base URL or local folder with JSON files")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    parser.add_argument("--strict", action="store_true", help="Treat missing artifacts as fatal")

    args = parser.parse_args(argv)

    exit_code = 0
    for filename in ARTIFACTS:
        try:
            payload = load_artifact(args.base_url, filename, args.timeout)
        except Exception as err:
            print(f"✗ {filename}: {err}", file=sys.stderr)
            if args.strict:
                exit_code = 1
            continue

        if isinstance(payload, list):
            count, first, last = describe_series(payload)
            print(
                f"✓ {filename}: {count} rows, range {format_dt(first)} → {format_dt(last)}",
            )
        else:
            print(f"✓ {filename}: loaded {type(payload).__name__} with {len(payload)} keys")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
