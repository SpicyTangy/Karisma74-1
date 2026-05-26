from __future__ import annotations

import json
from pathlib import Path


def append_manifest(path: str, entry: dict) -> None:
    """Aggiunge una riga JSON al manifest (una riga per PDF scaricato)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_manifest(path: str) -> dict:
    """Carica il manifest in un dict indicizzato per `file` (basename del PDF)."""
    result: dict = {}
    p = Path(path)
    if not p.exists():
        return result
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            result[entry["file"]] = entry
    return result
