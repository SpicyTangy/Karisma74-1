"""Verifica il flag --refresh di cmd_classify: ignora la cache e ri-classifica."""
import logging
import os
from argparse import Namespace

import tool

logger = logging.getLogger("test")


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls = 0

    def classify(self, pdf_path):
        self.calls += 1
        return {
            "file": os.path.basename(pdf_path), "status": "classificato",
            "fornitore_ok": True, "tipo_documento": "fattura", "tipo_label": "Fattura",
            "confidenza_classif": 0.9, "campi": {}, "errore": None,
        }


def _setup(tmp_path, monkeypatch):
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "2026-05-01_doc.pdf").write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(tool, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(tool, "PDF_DIR", pdf_dir)
    monkeypatch.setattr(tool, "MANIFEST_PATH", tmp_path / "manifest.jsonl")
    monkeypatch.setattr(tool, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setenv("APP_NAME", "x")
    monkeypatch.setenv("APP_PASSWORD", "y")
    monkeypatch.setenv("SUPPLIER_SLUG", "z")
    fake = FakeClient()
    monkeypatch.setattr(tool, "D74Client", lambda *a, **k: fake)
    return fake


def test_senza_refresh_usa_la_cache(tmp_path, monkeypatch):
    fake = _setup(tmp_path, monkeypatch)
    tool.cmd_classify(Namespace(refresh=False), logger)
    assert fake.calls == 1            # prima volta: classifica (cache vuota)
    tool.cmd_classify(Namespace(refresh=False), logger)
    assert fake.calls == 1            # seconda volta: presa dalla cache, non richiama


def test_con_refresh_ignora_la_cache(tmp_path, monkeypatch):
    fake = _setup(tmp_path, monkeypatch)
    tool.cmd_classify(Namespace(refresh=False), logger)
    assert fake.calls == 1            # popola la cache
    tool.cmd_classify(Namespace(refresh=True), logger)
    assert fake.calls == 2            # --refresh: ri-classifica ignorando la cache
