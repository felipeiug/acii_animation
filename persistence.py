"""Leitura e gravação atômica do status da exploração."""

from __future__ import annotations

import json
import os
from pathlib import Path

from explorer import Explorer

STATUS_PATH = Path(__file__).with_name("status.json")


def load_explorer(path: Path = STATUS_PATH) -> Explorer | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("seed"), int):
            return None
        return Explorer.from_snapshot(data)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_explorer(explorer: Explorer, path: Path = STATUS_PATH) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(explorer.snapshot(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
