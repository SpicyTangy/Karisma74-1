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


def _safe_json(response):
    try:
        return response.json()
    except Exception:
        return None


def _success_record(filename: str, data: dict) -> dict:
    sv = data.get("supplier_verification") or {}
    cls = data.get("classification") or {}
    return {
        "file": filename,
        "status": derive_status(data),
        "fornitore_ok": sv.get("belongs_to_supplier"),
        "tipo_documento": cls.get("document_type"),
        "tipo_label": cls.get("document_type_label"),
        "confidenza_classif": cls.get("confidence"),
        "campi": flatten_fields(data.get("extracted_fields")),
        "errore": None,
    }


def _error_record(filename: str, code, message) -> dict:
    return {
        "file": filename,
        "status": "errore",
        "fornitore_ok": None,
        "tipo_documento": None,
        "tipo_label": None,
        "confidenza_classif": None,
        "campi": {},
        "errore": f"{code}: {message}",
    }


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

    def _classify_once(self, pdf_path: str):
        with open(pdf_path, "rb") as fh:
            r = self.session.post(
                f"{self.base_url}/api/documents/classify-hybrid",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                data={"supplier": self.supplier},
                files={"file": (os.path.basename(pdf_path), fh, "application/pdf")},
                timeout=self.timeout,
            )
        return r.status_code, _safe_json(r)

    def classify(self, pdf_path: str) -> dict:
        if self.token is None:
            self.login()
        filename = os.path.basename(pdf_path)
        attempt = 0
        relogged = False
        while True:
            try:
                status, payload = self._classify_once(pdf_path)
            except requests.RequestException as exc:
                if attempt >= len(BACKOFF_DELAYS):
                    return _error_record(filename, "RETE", str(exc))
                self.sleep(BACKOFF_DELAYS[attempt])
                attempt += 1
                continue

            if status == 200 and isinstance(payload, dict) and payload.get("success"):
                return _success_record(filename, payload["data"])

            if status == 401:
                if relogged:
                    return _error_record(filename, "AUTH", "re-login fallito (401)")
                self.login()
                relogged = True
                continue

            if status == 422:
                err = payload.get("error", {}) if isinstance(payload, dict) else {}
                return _error_record(filename, err.get("code", "422"),
                                     err.get("message", "validazione/pipeline"))

            if status == 429 or 500 <= status < 600:
                if attempt >= len(BACKOFF_DELAYS):
                    err = payload.get("error", {}) if isinstance(payload, dict) else {}
                    return _error_record(filename, err.get("code", f"HTTP_{status}"),
                                         err.get("message", "errore server"))
                self.sleep(BACKOFF_DELAYS[attempt])
                attempt += 1
                continue

            return _error_record(filename, f"HTTP_{status}", str(payload))
