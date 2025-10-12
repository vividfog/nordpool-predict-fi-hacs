from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for entry in list(sys.path):
    if entry.startswith("__editable__.") and entry not in (str(ROOT),):
        try:
            Path(entry).resolve(strict=True)
        except (OSError, ValueError):
            sys.path.remove(entry)
