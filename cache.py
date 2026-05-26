from __future__ import annotations

import hashlib
import json
from pathlib import Path


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ResultCache:
    """Cache hash-file → record già classificato, persistita su JSON."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.data: dict = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, file_hash: str):
        return self.data.get(file_hash)

    def put(self, file_hash: str, record: dict) -> None:
        self.data[file_hash] = record

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
