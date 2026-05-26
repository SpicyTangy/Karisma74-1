from __future__ import annotations

import os
import time

import requests

BACKOFF_DELAYS = [2, 5, 15]

LOW_CONFIDENCE_THRESHOLD = 0.7


def derive_status(data: dict) -> str:
    """Mappa il `data` di una risposta 200 in uno stato (MD §5.3).

    Ritorna: classificato | non_pertinente | tipo_sconosciuto | bassa_confidenza.
    """
    sv = data.get("supplier_verification") or {}
    if not sv.get("belongs_to_supplier"):
        return "non_pertinente"
    cls = data.get("classification") or {}
    dtype = cls.get("document_type")
    if dtype is None or dtype == "non_classificabile":
        return "tipo_sconosciuto"
    conf = cls.get("confidence")
    if conf is not None and conf < LOW_CONFIDENCE_THRESHOLD:
        return "bassa_confidenza"
    return "classificato"


def flatten_fields(extracted_fields: dict | None) -> dict:
    """Trasforma {key: {value, confidence}} in {key: value}. None/vuoto → {}."""
    if not extracted_fields:
        return {}
    out: dict = {}
    for key, val in extracted_fields.items():
        out[key] = val.get("value") if isinstance(val, dict) else val
    return out


class D74Client:
    def __init__(self, base_url, app_name, password, supplier,
                 timeout=120, session=None, sleep=time.sleep):
        self.base_url = base_url.rstrip("/")
        self.app_name = app_name
        self.password = password
        self.supplier = supplier
        self.timeout = timeout
        self.session = session or requests.Session()
        self.sleep = sleep
        self.token = None

    def login(self) -> str:
        r = self.session.post(
            f"{self.base_url}/api/auth/login",
            json={"app_name": self.app_name, "password": self.password},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        self.token = r.json()["token"]
        return self.token
