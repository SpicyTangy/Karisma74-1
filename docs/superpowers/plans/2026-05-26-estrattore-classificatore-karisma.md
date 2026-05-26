# Estrattore email + classificatore documenti (Karisma) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaricare i PDF allegati alle email di un fornitore da Gmail e, per ciascun PDF, ottenere classificazione e campi estratti dall'API d74-service (`classify-hybrid`), producendo un Excel di riepilogo.

**Architecture:** Due fasi (`download`, `classify`, oppure `all`) in un'unica CLI a più moduli. La fase `download` riusa la plumbing OAuth2/IMAP del template del collega e scrive i PDF + un `manifest.jsonl` con i metadati email. La fase `classify` rilegge i PDF, li invia all'API con retry/backoff e cache anti-spreco (hash SHA-256), e scrive l'Excel con colonne dinamiche.

**Tech Stack:** Python 3.10+, `requests`, `openpyxl`, `python-dotenv`, `google-auth`, `google-auth-oauthlib`, `pytest` (dev).

**Riferimenti:** spec in `docs/superpowers/specs/2026-05-26-estrattore-classificatore-karisma-design.md`; API in `templates/integrazione-classify-hybrid (1).md`; codice base in `templates/email_extractor_template.py`.

---

## Struttura dei file (a regime, nella root del repo)

```
tool.py             ← CLI: download / classify / all, orchestrazione, env
gmail_fetch.py      ← build_gmail_query, fetch_emails, download_pdfs (dal template)
d74_client.py       ← D74Client (login, classify), derive_status, flatten_fields
excel_writer.py     ← FIXED_COLUMNS, collect_field_columns, write_excel
manifest.py         ← append_manifest, load_manifest (collante download↔classify)
cache.py            ← file_sha256, ResultCache
requirements.txt    ← dipendenze runtime
requirements-dev.txt← pytest
tests/              ← test unitari
output/             ← pdf/, manifest.jsonl, cache.json, risultati_*.xlsx (gitignored)
```

**Schema record** (prodotto da `D74Client.classify`, arricchito dall'orchestratore, consumato da `excel_writer`):

```python
{
    "file": "2026-05-12_doc.pdf",     # basename del PDF
    "file_hash": "<sha256>",          # aggiunto dall'orchestratore
    "data_email": "", "mittente": "", "oggetto": "",  # dal manifest
    "status": "classificato|non_pertinente|tipo_sconosciuto|bassa_confidenza|errore",
    "fornitore_ok": True | False | None,
    "tipo_documento": "fattura" | None,
    "tipo_label": "Fattura" | None,
    "confidenza_classif": 0.92 | None,
    "campi": {"numero_prenotazione": "ABC123", ...},  # extracted_fields appiattiti
    "errore": None | "CODICE: messaggio",
}
```

---

### Task 1: Scaffolding progetto e dipendenze

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Scrivere `requirements.txt`**

```
openpyxl==3.1.2
python-dotenv==1.0.1
google-auth>=2.0.0
google-auth-oauthlib>=1.0.0
requests>=2.31.0
```

- [ ] **Step 2: Scrivere `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0.0
```

- [ ] **Step 3: Creare `tests/__init__.py` (file vuoto) e un test di smoke `tests/test_smoke.py`**

```python
def test_smoke():
    assert True
```

- [ ] **Step 4: Installare le dipendenze e verificare che pytest giri**

Run:
```
pip install -r requirements-dev.txt
python -m pytest tests/test_smoke.py -v
```
Expected: PASS (`test_smoke PASSED`).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt requirements-dev.txt tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffolding progetto + pytest"
```

---

### Task 2: `gmail_fetch.build_gmail_query` (logica pura)

**Files:**
- Create: `gmail_fetch.py`
- Test: `tests/test_gmail_query.py`

- [ ] **Step 1: Scrivere il test che fallisce**

```python
from datetime import date
from gmail_fetch import build_gmail_query

def test_build_gmail_query_aggiunge_after_e_before_inclusivo():
    # before è esclusivo lato Gmail → il codice somma 1 giorno a to_date
    q = build_gmail_query("from:fornitore has:attachment", date(2026, 1, 1), date(2026, 5, 31))
    assert q == "from:fornitore has:attachment after:2026/01/01 before:2026/06/01"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `python -m pytest tests/test_gmail_query.py -v`
Expected: FAIL (`ModuleNotFoundError` o `ImportError: cannot import name 'build_gmail_query'`).

- [ ] **Step 3: Implementare `build_gmail_query` in `gmail_fetch.py`**

```python
from __future__ import annotations

from datetime import date, timedelta


def build_gmail_query(search_query: str, from_date: date, to_date: date) -> str:
    """Aggiunge gli operatori after:/before: alla query Gmail.

    before: è esclusivo lato Gmail, quindi sommiamo 1 giorno a to_date per
    rendere il range [from_date, to_date] inclusivo su entrambi gli estremi.
    """
    after = from_date.strftime("%Y/%m/%d")
    before = (to_date + timedelta(days=1)).strftime("%Y/%m/%d")
    return f"{search_query} after:{after} before:{before}"
```

- [ ] **Step 4: Eseguire il test e verificare che passi**

Run: `python -m pytest tests/test_gmail_query.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gmail_fetch.py tests/test_gmail_query.py
git commit -m "feat: build_gmail_query con range date inclusivo"
```

---

### Task 3: `d74_client.derive_status` (logica pura)

**Files:**
- Create: `d74_client.py`
- Test: `tests/test_derive_status.py`

- [ ] **Step 1: Scrivere i test che falliscono (i 5 scenari del MD §5.3 + bassa confidenza)**

```python
from d74_client import derive_status

def _data(belongs, dtype, conf):
    return {
        "supplier_verification": {"belongs_to_supplier": belongs},
        "classification": {"document_type": dtype, "confidence": conf},
    }

def test_ok_pieno():
    assert derive_status(_data(True, "fattura", 0.92)) == "classificato"

def test_non_del_fornitore():
    assert derive_status(_data(False, None, None)) == "non_pertinente"

def test_tipo_non_classificabile():
    assert derive_status(_data(True, "non_classificabile", None)) == "tipo_sconosciuto"

def test_document_type_null():
    assert derive_status(_data(True, None, None)) == "tipo_sconosciuto"

def test_bassa_confidenza():
    assert derive_status(_data(True, "fattura", 0.4)) == "bassa_confidenza"

def test_strutture_mancanti_non_esplodono():
    assert derive_status({}) == "non_pertinente"
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_derive_status.py -v`
Expected: FAIL (`ImportError: cannot import name 'derive_status'`).

- [ ] **Step 3: Implementare `derive_status` in `d74_client.py`**

```python
from __future__ import annotations

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
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `python -m pytest tests/test_derive_status.py -v`
Expected: PASS (6 test).

- [ ] **Step 5: Commit**

```bash
git add d74_client.py tests/test_derive_status.py
git commit -m "feat: derive_status per gli esiti classify-hybrid"
```

---

### Task 4: `d74_client.flatten_fields` (logica pura)

**Files:**
- Modify: `d74_client.py`
- Test: `tests/test_flatten_fields.py`

- [ ] **Step 1: Scrivere i test che falliscono**

```python
from d74_client import flatten_fields

def test_appiattisce_value():
    fields = {
        "numero": {"value": "ABC123", "confidence": 0.99},
        "data": {"value": "2026-07-12", "confidence": 0.97},
    }
    assert flatten_fields(fields) == {"numero": "ABC123", "data": "2026-07-12"}

def test_none_ritorna_dict_vuoto():
    assert flatten_fields(None) == {}

def test_dict_vuoto_ritorna_dict_vuoto():
    assert flatten_fields({}) == {}
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_flatten_fields.py -v`
Expected: FAIL (`ImportError: cannot import name 'flatten_fields'`).

- [ ] **Step 3: Aggiungere `flatten_fields` in `d74_client.py`**

```python
def flatten_fields(extracted_fields: dict | None) -> dict:
    """Trasforma {key: {value, confidence}} in {key: value}. None/vuoto → {}."""
    if not extracted_fields:
        return {}
    out: dict = {}
    for key, val in extracted_fields.items():
        out[key] = val.get("value") if isinstance(val, dict) else val
    return out
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `python -m pytest tests/test_flatten_fields.py -v`
Expected: PASS (3 test).

- [ ] **Step 5: Commit**

```bash
git add d74_client.py tests/test_flatten_fields.py
git commit -m "feat: flatten_fields per i campi estratti"
```

---

### Task 5: `D74Client.login` (con session mockata)

**Files:**
- Modify: `d74_client.py`
- Test: `tests/test_d74_login.py`

- [ ] **Step 1: Scrivere il test che fallisce**

```python
from unittest.mock import MagicMock
from d74_client import D74Client

def _resp(status, json_data):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m

def test_login_salva_e_ritorna_il_token():
    session = MagicMock()
    session.post.return_value = _resp(200, {"token": "tok-123"})
    client = D74Client("https://x", "app", "pwd", "slug", session=session)

    token = client.login()

    assert token == "tok-123"
    assert client.token == "tok-123"
    args, kwargs = session.post.call_args
    assert args[0] == "https://x/api/auth/login"
    assert kwargs["json"] == {"app_name": "app", "password": "pwd"}
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `python -m pytest tests/test_d74_login.py -v`
Expected: FAIL (`ImportError: cannot import name 'D74Client'`).

- [ ] **Step 3: Implementare lo scheletro di `D74Client` + `login` in `d74_client.py`**

Aggiungere in cima al file:
```python
import os
import time

import requests

BACKOFF_DELAYS = [2, 5, 15]


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
```

- [ ] **Step 4: Eseguire il test e verificare che passi**

Run: `python -m pytest tests/test_d74_login.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add d74_client.py tests/test_d74_login.py
git commit -m "feat: D74Client.login"
```

---

### Task 6: `D74Client.classify` — percorso felice (200 → record)

**Files:**
- Modify: `d74_client.py`
- Test: `tests/test_d74_classify_ok.py`

- [ ] **Step 1: Scrivere il test che fallisce**

```python
from unittest.mock import MagicMock
from d74_client import D74Client

def _resp(status, json_data):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m

SUCCESS = {
    "success": True,
    "data": {
        "supplier_verification": {"belongs_to_supplier": True, "confidence": 0.95},
        "classification": {"document_type": "fattura", "document_type_label": "Fattura", "confidence": 0.92},
        "extracted_fields": {"numero": {"value": "ABC123", "confidence": 0.99}},
    },
}

def test_classify_costruisce_record_da_200(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    session = MagicMock()
    session.post.return_value = _resp(200, SUCCESS)
    client = D74Client("https://x", "app", "pwd", "slug", session=session)
    client.token = "tok"  # salta il login

    rec = client.classify(str(pdf))

    assert rec["file"] == "doc.pdf"
    assert rec["status"] == "classificato"
    assert rec["fornitore_ok"] is True
    assert rec["tipo_documento"] == "fattura"
    assert rec["tipo_label"] == "Fattura"
    assert rec["confidenza_classif"] == 0.92
    assert rec["campi"] == {"numero": "ABC123"}
    assert rec["errore"] is None
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `python -m pytest tests/test_d74_classify_ok.py -v`
Expected: FAIL (`AttributeError: 'D74Client' object has no attribute 'classify'`).

- [ ] **Step 3: Implementare `_classify_once`, i builder di record e `classify` in `d74_client.py`**

```python
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
```

Aggiungere come metodi della classe `D74Client`:
```python
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
```

- [ ] **Step 4: Eseguire il test e verificare che passi**

Run: `python -m pytest tests/test_d74_classify_ok.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add d74_client.py tests/test_d74_classify_ok.py
git commit -m "feat: D74Client.classify percorso felice"
```

---

### Task 7: `D74Client.classify` — gestione errori (401 / 422 / 5xx)

**Files:**
- Test: `tests/test_d74_classify_errori.py`

> Nessuna modifica al codice: la logica è già in `classify` (Task 6). Questi test la blindano.

- [ ] **Step 1: Scrivere i test che falliscono se la logica errori è sbagliata**

```python
from unittest.mock import MagicMock
from d74_client import D74Client

def _resp(status, json_data):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m

SUCCESS = {
    "success": True,
    "data": {
        "supplier_verification": {"belongs_to_supplier": True},
        "classification": {"document_type": "fattura", "document_type_label": "Fattura", "confidence": 0.9},
        "extracted_fields": {},
    },
}

def _pdf(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return str(p)

def test_401_poi_relogin_poi_successo(tmp_path):
    session = MagicMock()
    # 1) classify→401, 2) login→token, 3) classify→200
    session.post.side_effect = [
        _resp(401, {"message": "Unauthenticated."}),
        _resp(200, {"token": "tok-nuovo"}),
        _resp(200, SUCCESS),
    ]
    client = D74Client("https://x", "app", "pwd", "slug", session=session)
    client.token = "tok-vecchio"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "classificato"
    assert client.token == "tok-nuovo"

def test_401_due_volte_da_errore_auth(tmp_path):
    session = MagicMock()
    session.post.side_effect = [
        _resp(401, {"message": "Unauthenticated."}),
        _resp(200, {"token": "tok-nuovo"}),
        _resp(401, {"message": "Unauthenticated."}),
    ]
    client = D74Client("https://x", "app", "pwd", "slug", session=session)
    client.token = "tok"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "errore"
    assert rec["errore"].startswith("AUTH")

def test_422_non_ritenta_e_logga_codice(tmp_path):
    session = MagicMock()
    session.post.return_value = _resp(422, {"success": False, "error": {"code": "FILE_TOO_LARGE", "message": "troppo grande"}})
    client = D74Client("https://x", "app", "pwd", "slug", session=session)
    client.token = "tok"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "errore"
    assert rec["errore"] == "FILE_TOO_LARGE: troppo grande"
    assert session.post.call_count == 1  # nessun retry

def test_5xx_backoff_poi_successo(tmp_path):
    calls = []
    session = MagicMock()
    session.post.side_effect = [
        _resp(500, {"success": False, "error": {"code": "INTERNAL_ERROR", "message": "boom"}}),
        _resp(200, SUCCESS),
    ]
    client = D74Client("https://x", "app", "pwd", "slug", session=session,
                       sleep=lambda s: calls.append(s))
    client.token = "tok"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "classificato"
    assert calls == [2]  # un solo backoff da 2s

def test_5xx_esaurisce_i_retry(tmp_path):
    session = MagicMock()
    session.post.side_effect = [
        _resp(500, {"success": False, "error": {"code": "INTERNAL_ERROR", "message": "boom"}})
        for _ in range(4)
    ]
    client = D74Client("https://x", "app", "pwd", "slug", session=session,
                       sleep=lambda s: None)
    client.token = "tok"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "errore"
    assert rec["errore"].startswith("INTERNAL_ERROR")
    assert session.post.call_count == 4  # 1 + 3 retry
```

- [ ] **Step 2: Eseguire i test**

Run: `python -m pytest tests/test_d74_classify_errori.py -v`
Expected: PASS (5 test). Se qualcuno fallisce, correggere la logica in `classify` (Task 6 Step 3) finché passano — non modificare i test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_d74_classify_errori.py
git commit -m "test: gestione errori D74Client.classify (401/422/5xx)"
```

---

### Task 8: `excel_writer` — colonne fisse + dinamiche

**Files:**
- Create: `excel_writer.py`
- Test: `tests/test_excel_writer.py`

- [ ] **Step 1: Scrivere i test che falliscono**

```python
from openpyxl import load_workbook
from excel_writer import FIXED_COLUMNS, collect_field_columns, write_excel

def test_collect_field_columns_unione_ordinata():
    records = [
        {"campi": {"numero": "1", "data": "x"}},
        {"campi": {"numero": "2", "passeggero": "y"}},
        {"campi": None},
    ]
    assert collect_field_columns(records) == ["data", "numero", "passeggero"]

def test_write_excel_intestazioni_e_valori(tmp_path):
    records = [
        {
            "file": "doc.pdf", "data_email": "2026-05-12", "mittente": "a@b.it",
            "oggetto": "Fattura", "status": "classificato", "fornitore_ok": True,
            "tipo_documento": "fattura", "tipo_label": "Fattura",
            "confidenza_classif": 0.92, "errore": None,
            "campi": {"numero": "ABC123"},
        }
    ]
    out = tmp_path / "ris.xlsx"
    write_excel(records, str(out))

    wb = load_workbook(out)
    ws = wb.active
    headers = [c.value for c in ws[1]]
    assert headers == FIXED_COLUMNS + ["numero"]
    row = [c.value for c in ws[2]]
    assert row[headers.index("file")] == "doc.pdf"
    assert row[headers.index("numero")] == "ABC123"
    # None normalizzato a stringa vuota
    assert row[headers.index("errore")] == ""
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_excel_writer.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'excel_writer'`).

- [ ] **Step 3: Implementare `excel_writer.py`**

```python
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

FIXED_COLUMNS = [
    "file", "data_email", "mittente", "oggetto", "status", "fornitore_ok",
    "tipo_documento", "tipo_label", "confidenza_classif", "errore",
]


def collect_field_columns(records: list[dict]) -> list[str]:
    """Unione ordinata di tutte le chiavi presenti nei `campi` dei record."""
    keys: set[str] = set()
    for rec in records:
        keys.update((rec.get("campi") or {}).keys())
    return sorted(keys)


def write_excel(records: list[dict], path: str) -> None:
    field_cols = collect_field_columns(records)
    headers = FIXED_COLUMNS + field_cols

    wb = Workbook()
    ws = wb.active
    ws.title = "Risultati"
    ws.append(headers)

    for rec in records:
        campi = rec.get("campi") or {}
        values = [rec.get(col) for col in FIXED_COLUMNS] + [campi.get(col) for col in field_cols]
        ws.append(["" if v is None else v for v in values])

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `python -m pytest tests/test_excel_writer.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add excel_writer.py tests/test_excel_writer.py
git commit -m "feat: excel_writer con colonne dinamiche"
```

---

### Task 9: `manifest` — collante tra download e classify

**Files:**
- Create: `manifest.py`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Scrivere i test che falliscono**

```python
from manifest import append_manifest, load_manifest

def test_append_e_load_roundtrip(tmp_path):
    path = tmp_path / "manifest.jsonl"
    append_manifest(str(path), {"file": "a.pdf", "data_email": "2026-05-12", "mittente": "x@y.it", "oggetto": "Ciao"})
    append_manifest(str(path), {"file": "b.pdf", "data_email": "2026-05-13", "mittente": "z@y.it", "oggetto": "Altro"})

    loaded = load_manifest(str(path))

    assert set(loaded.keys()) == {"a.pdf", "b.pdf"}
    assert loaded["a.pdf"]["oggetto"] == "Ciao"

def test_load_manifest_inesistente_ritorna_vuoto(tmp_path):
    assert load_manifest(str(tmp_path / "manca.jsonl")) == {}
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_manifest.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'manifest'`).

- [ ] **Step 3: Implementare `manifest.py`**

```python
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
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `python -m pytest tests/test_manifest.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add manifest.py tests/test_manifest.py
git commit -m "feat: manifest jsonl per i metadati email"
```

---

### Task 10: `cache` — hash file + ResultCache

**Files:**
- Create: `cache.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Scrivere i test che falliscono**

```python
from cache import file_sha256, ResultCache

def test_file_sha256_deterministico(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"contenuto")
    h1 = file_sha256(str(f))
    h2 = file_sha256(str(f))
    assert h1 == h2 and len(h1) == 64

def test_cache_put_get_save_reload(tmp_path):
    path = tmp_path / "cache.json"
    c = ResultCache(str(path))
    assert c.get("abc") is None
    c.put("abc", {"status": "classificato"})
    c.save()

    c2 = ResultCache(str(path))
    assert c2.get("abc") == {"status": "classificato"}
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_cache.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'cache'`).

- [ ] **Step 3: Implementare `cache.py`**

```python
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
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `python -m pytest tests/test_cache.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add cache.py tests/test_cache.py
git commit -m "feat: cache hash-file per evitare ri-classificazioni"
```

---

### Task 11: `gmail_fetch` — fetch email + download PDF (port dal template)

**Files:**
- Modify: `gmail_fetch.py`

> Porting delle funzioni dal template del collega, adattate per essere importabili. `SEARCH_QUERY` diventa configurabile via env. Niente test automatici qui (IMAP/rete reale): verifica manuale nel Task 14.

- [ ] **Step 1: Aggiungere a `gmail_fetch.py` import, costanti e helper OAuth2**

```python
import email as email_lib
import imaplib
import logging
import os
import re
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
_INVALID = re.compile(r'[<>:"/\\|?*]')

_MESI_IT = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
}

# Query Gmail del fornitore. Override con env GMAIL_SEARCH_QUERY se presente.
DEFAULT_SEARCH_QUERY = "has:attachment"


def get_search_query() -> str:
    return os.getenv("GMAIL_SEARCH_QUERY", DEFAULT_SEARCH_QUERY)


def _get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://mail.google.com/"],
    )
    creds.refresh(Request())
    return creds.token


def _build_xoauth2_string(user: str, access_token: str) -> bytes:
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01".encode()
```

- [ ] **Step 2: Aggiungere `fetch_emails` (porting dal template, usa `build_gmail_query`)**

```python
def fetch_emails(user, client_id, client_secret, refresh_token,
                 from_date, to_date, search_query, logger) -> list[Message]:
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    except OSError as exc:
        logger.error("Connessione IMAP fallita: %s", exc)
        raise SystemExit(1)

    try:
        access_token = _get_access_token(client_id, client_secret, refresh_token)
        xoauth2 = _build_xoauth2_string(user, access_token)
        imap.authenticate("XOAUTH2", lambda _: xoauth2)
    except imaplib.IMAP4.error as exc:
        logger.error("Autenticazione IMAP fallita: %s", exc)
        raise SystemExit(1)
    except Exception as exc:
        logger.error("Errore credenziali OAuth2: %s", exc)
        raise SystemExit(1)

    try:
        for folder in ('"[Gmail]/Tutti i messaggi"', "INBOX"):
            try:
                status, _ = imap.select(folder, readonly=True)
            except imaplib.IMAP4.error:
                status = "NO"
            if status == "OK":
                logger.info("Cartella selezionata: %s", folder)
                break
        else:
            logger.error("Impossibile selezionare una cartella IMAP valida")
            raise SystemExit(1)

        gm_query = build_gmail_query(search_query, from_date, to_date)
        try:
            _, data = imap.search(None, f'X-GM-RAW "{gm_query}"')
            logger.info("Ricerca Gmail: %s", gm_query)
        except imaplib.IMAP4.error:
            since = from_date.strftime("%d-%b-%Y")
            bef = (to_date + timedelta(days=1)).strftime("%d-%b-%Y")
            _, data = imap.search(None, f"SINCE {since} BEFORE {bef}")
            logger.info("Ricerca IMAP standard (fallback solo data)")

        uids = data[0].split() if data and data[0] else []
        logger.info("Email trovate: %d", len(uids))
        if not uids:
            return []

        batch_size = 50
        messages: list[Message] = []
        for i in range(0, len(uids), batch_size):
            batch = uids[i:i + batch_size]
            _, responses = imap.fetch(b",".join(batch), "(RFC822)")
            for item in responses:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                try:
                    messages.append(email_lib.message_from_bytes(item[1]))
                except Exception as exc:
                    logger.warning("Mail non parsabile: %s — saltata", exc)
            logger.info("Download: %d/%d", min(i + batch_size, len(uids)), len(uids))
    finally:
        imap.logout()

    def _date_key(m: Message) -> float:
        try:
            return parsedate_to_datetime(m.get("Date", "")).timestamp()
        except Exception:
            return 0.0

    messages.sort(key=_date_key)
    return messages
```

- [ ] **Step 3: Aggiungere `download_pdfs` (porting dal template)**

```python
def download_pdfs(msg: Message, pdf_dir: Path, logger) -> list[Path]:
    try:
        dt = parsedate_to_datetime(msg.get("Date", ""))
        year, month = str(dt.year), f"{dt.month:02d}-{_MESI_IT[dt.month]}"
        date_prefix = dt.strftime("%Y-%m-%d")
    except Exception:
        year, month, date_prefix = "sconosciuto", "00-Sconosciuto", "0000-00-00"

    dest_dir = pdf_dir / year / month
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    for part in msg.walk():
        ct = part.get_content_type()
        filename = part.get_filename() or ""
        is_pdf = ct == "application/pdf" or (
            ct == "application/octet-stream" and filename.lower().endswith(".pdf")
        )
        if not is_pdf or not filename:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if len(payload) > MAX_PDF_BYTES:
            logger.warning("PDF oversize (%d MB): %s — saltato", len(payload) // (1024 * 1024), filename)
            continue

        safe = _INVALID.sub("_", Path(filename).name)
        pdf_path = dest_dir / f"{date_prefix}_{safe}"
        pdf_path.write_bytes(payload)
        saved.append(pdf_path)
        logger.info("PDF salvato: %s", pdf_path)
    return saved
```

- [ ] **Step 4: Verificare che l'import del modulo non sia rotto e che i test esistenti passino**

Run: `python -c "import gmail_fetch" && python -m pytest tests/test_gmail_query.py -v`
Expected: nessun errore di import; `test_gmail_query` PASS.

- [ ] **Step 5: Commit**

```bash
git add gmail_fetch.py
git commit -m "feat: gmail_fetch (fetch_emails, download_pdfs) dal template"
```

---

### Task 12: `tool.py` — CLI e orchestrazione

**Files:**
- Create: `tool.py`

> Wiring dei moduli. Verifica reale (rete/credenziali) nel Task 14; qui si verifica solo che la CLI parta e mostri l'help.

- [ ] **Step 1: Implementare `tool.py`**

```python
"""CLI estrattore email + classificatore documenti (Karisma).

Comandi:
  download  scarica i PDF dalle email del fornitore (+ manifest metadati)
  classify  invia i PDF all'API d74-service e scrive l'Excel
  all       download seguito da classify
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

import gmail_fetch
from cache import ResultCache, file_sha256
from d74_client import D74Client
from excel_writer import write_excel
from manifest import append_manifest, load_manifest

OUTPUT_DIR = Path("output")
PDF_DIR = OUTPUT_DIR / "pdf"
MANIFEST_PATH = OUTPUT_DIR / "manifest.jsonl"
CACHE_PATH = OUTPUT_DIR / "cache.json"
MAX_PDF_BYTES = 20 * 1024 * 1024
DEFAULT_BASE_URL = "https://services.d74.cloud"


def get_logger() -> logging.Logger:
    logger = logging.getLogger("karisma")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Variabile {name} mancante nel file .env")
    return value


def cmd_download(args, logger) -> None:
    from email.utils import parsedate_to_datetime

    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date)
    logger.info("Download email dal %s al %s…", from_date, to_date)

    messages = gmail_fetch.fetch_emails(
        _require_env("GMAIL_USER"),
        _require_env("GMAIL_CLIENT_ID"),
        _require_env("GMAIL_CLIENT_SECRET"),
        _require_env("GMAIL_REFRESH_TOKEN"),
        from_date, to_date, gmail_fetch.get_search_query(), logger,
    )

    total = 0
    for msg in messages:
        try:
            mail_date = parsedate_to_datetime(msg.get("Date", "")).isoformat()
        except Exception:
            mail_date = ""
        for pdf_path in gmail_fetch.download_pdfs(msg, PDF_DIR, logger):
            append_manifest(str(MANIFEST_PATH), {
                "file": pdf_path.name,
                "data_email": mail_date,
                "mittente": msg.get("From", ""),
                "oggetto": msg.get("Subject", ""),
            })
            total += 1
    logger.info("PDF scaricati: %d (manifest: %s)", total, MANIFEST_PATH)


def cmd_classify(args, logger) -> None:
    base_url = os.getenv("D74_BASE_URL", DEFAULT_BASE_URL)
    client = D74Client(
        base_url,
        _require_env("APP_NAME"),
        _require_env("APP_PASSWORD"),
        _require_env("SUPPLIER_SLUG"),
    )
    manifest = load_manifest(str(MANIFEST_PATH))
    cache = ResultCache(str(CACHE_PATH))

    records: list[dict] = []
    pdfs = sorted(PDF_DIR.rglob("*.pdf"))
    logger.info("PDF da classificare: %d", len(pdfs))

    for pdf in pdfs:
        if pdf.stat().st_size > MAX_PDF_BYTES:
            logger.warning("PDF oversize, saltato: %s", pdf.name)
            continue
        file_hash = file_sha256(str(pdf))
        record = cache.get(file_hash)
        if record is None:
            logger.info("Classifico: %s", pdf.name)
            record = client.classify(str(pdf))
            record["file_hash"] = file_hash
            cache.put(file_hash, record)
            cache.save()
        else:
            logger.info("Da cache: %s", pdf.name)

        meta = manifest.get(pdf.name, {})
        records.append({
            **record,
            "data_email": meta.get("data_email", ""),
            "mittente": meta.get("mittente", ""),
            "oggetto": meta.get("oggetto", ""),
        })

    run_date = date.today().strftime("%Y%m%d")
    excel_path = OUTPUT_DIR / f"risultati_{run_date}.xlsx"
    write_excel(records, str(excel_path))
    logger.info("Excel scritto: %s (%d righe)", excel_path, len(records))


def cmd_all(args, logger) -> None:
    cmd_download(args, logger)
    cmd_classify(args, logger)


def parse_args() -> argparse.Namespace:
    to_default = date.today()
    from_default = to_default - timedelta(days=30)
    parser = argparse.ArgumentParser(description="Estrattore email + classificatore documenti.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("download", "classify", "all"):
        sp = sub.add_parser(name)
        sp.add_argument("--from", dest="from_date", default=from_default.isoformat(), metavar="YYYY-MM-DD")
        sp.add_argument("--to", dest="to_date", default=to_default.isoformat(), metavar="YYYY-MM-DD")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    logger = get_logger()
    args = parse_args()
    {"download": cmd_download, "classify": cmd_classify, "all": cmd_all}[args.command](args, logger)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verificare che la CLI parta e mostri l'help dei sottocomandi**

Run: `python tool.py --help` poi `python tool.py classify --help`
Expected: nessun traceback; viene mostrato l'help con i comandi `download/classify/all` e le opzioni `--from/--to`.

- [ ] **Step 3: Commit**

```bash
git add tool.py
git commit -m "feat: CLI tool.py (download/classify/all)"
```

---

### Task 13: `.env.example`, `.gitignore`, README di utilizzo

**Files:**
- Create: `.env.example` (nella root)
- Modify: `.gitignore`
- Create: `README.md` (nella root)

- [ ] **Step 1: Creare `.env.example` nella root**

```
# Gmail — OAuth2 (stesso account del template)
GMAIL_USER=
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REFRESH_TOKEN=
# Query di ricerca Gmail del fornitore (es. "from:fornitore has:attachment")
GMAIL_SEARCH_QUERY=

# API d74-service (classify-hybrid)
APP_NAME=
APP_PASSWORD=
SUPPLIER_SLUG=
# Opzionale: override base URL (default https://services.d74.cloud)
D74_BASE_URL=
```

- [ ] **Step 2: Verificare che `.gitignore` (root) escluda `.env` e `output/`**

Run: `python -m pytest -q` (sanity) e poi controllare a vista che `.gitignore` contenga già le righe `.env` e `output/` (create in fase di setup repo). Se mancano, aggiungerle.

- [ ] **Step 3: Creare `README.md` nella root**

````markdown
# Karisma74 — Estrattore email + classificatore documenti

Scarica i PDF allegati alle email di un fornitore da Gmail e li classifica
tramite l'API d74-service (`classify-hybrid`), producendo un Excel.

## Setup

```
pip install -r requirements.txt
copy .env.example .env   # poi compilare i valori
```

`.env` — credenziali Gmail OAuth2 + API d74 (`APP_NAME`, `APP_PASSWORD`,
`SUPPLIER_SLUG`). Vedi `.env.example`. **Non committare `.env`.**

Imposta la query del fornitore in `GMAIL_SEARCH_QUERY` (sintassi di ricerca
Gmail, es. `from:fornitore has:attachment`).

## Uso

```
python tool.py download --from 2026-01-01 --to 2026-05-31   # solo scarico PDF
python tool.py classify                                     # classifico + Excel
python tool.py all --from 2026-01-01 --to 2026-05-31        # tutto in fila
```

Output in `output/`: PDF in `pdf/<anno>/<mese>/`, riepilogo in
`risultati_YYYYMMDD.xlsx`. La cache (`output/cache.json`) evita di
ri-classificare (e ri-pagare) PDF già processati.

## Test

```
pip install -r requirements-dev.txt
python -m pytest -v
```
````

- [ ] **Step 4: Eseguire l'intera suite di test**

Run: `python -m pytest -v`
Expected: tutti i test PASS.

- [ ] **Step 5: Commit**

```bash
git add .env.example README.md .gitignore
git commit -m "docs: .env.example, README, gitignore"
```

---

### Task 14: Verifica end-to-end manuale (con credenziali reali)

> Richiede le credenziali nel `.env` e rete. Da fare insieme all'utente. Non è automatizzabile.

- [ ] **Step 1: Compilare `.env`** con i valori Gmail + `APP_NAME`/`APP_PASSWORD`/`SUPPLIER_SLUG` + `GMAIL_SEARCH_QUERY` del fornitore.

- [ ] **Step 2: Scaricare un periodo ristretto** (per non tirare giù troppo):

Run: `python tool.py download --from 2026-05-01 --to 2026-05-26`
Expected: log "PDF scaricati: N"; file in `output/pdf/...`; `output/manifest.jsonl` popolato.

- [ ] **Step 3: Ispezionare i PDF scaricati** a mano: sono davvero del fornitore giusto?

- [ ] **Step 4: Classificare (serial)**:

Run: `python tool.py classify`
Expected: log per file ("Classifico: …"); `output/risultati_YYYYMMDD.xlsx` creato.

- [ ] **Step 5: Aprire l'Excel** e verificare: colonna `status` coerente, campi estratti nelle colonne dinamiche, errori visibili nella colonna `errore`. Verificare che un secondo `classify` usi la cache ("Da cache: …").

- [ ] **Step 6: Commit finale (se sono serviti aggiustamenti) e push**

```bash
git add -A
git commit -m "chore: aggiustamenti post verifica end-to-end"
git push
```

---

## Self-Review (eseguito a fine stesura)

- **Copertura spec:** fetch Gmail → Task 11; download PDF → Task 11/12; manifest metadati → Task 9/12; client API + login → Task 5; classify + retry/backoff/relogin → Task 6/7; derive_status §5.3 → Task 3; campi estratti dinamici → Task 4/8; Excel colonne fisse+dinamiche → Task 8; cache hash anti-spreco → Task 10; filtro >20MB / solo PDF → Task 11 (download) + Task 12 (classify); `.env` (rimozione `GMAIL_ACCOUNT_PASSWORD`, nuove var) → Task 13; testing logica pura → Task 2/3/4/6/7/8/9/10; verifica manuale rete → Task 14. Nessuna lacuna.
- **Placeholder:** nessun TBD/TODO; ogni step di codice ha codice reale.
- **Consistenza tipi/firme:** `D74Client(base_url, app_name, password, supplier, timeout, session, sleep)`, `.login()`, `.classify(pdf_path)→record`, `derive_status(data)`, `flatten_fields(extracted_fields)`, `write_excel(records, path)`, `collect_field_columns(records)`, `FIXED_COLUMNS`, `append_manifest(path, entry)`/`load_manifest(path)`, `file_sha256(path)`/`ResultCache(path)` — coerenti tra tutti i task e con `tool.py`.
