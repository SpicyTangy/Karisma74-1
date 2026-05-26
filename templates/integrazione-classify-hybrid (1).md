# Integrazione API d74-service — Classificazione documenti (endpoint `classify-hybrid`)

Documento tecnico di riferimento per implementare un client che invii in batch una serie di documenti PDF al servizio d74-service e raccolga gli esiti della classificazione e dell'estrazione campi.

Pubblico di riferimento: agente / sviluppatore che deve scrivere il codice del client.

---

## 1. Informazioni generali

- **Base URL produzione**: `https://services.d74.cloud`
- **Protocollo**: HTTPS
- **Formato dati**: JSON in input/output (con eccezione del multipart per l'upload file)
- **Autenticazione**: OAuth2 Bearer Token (Laravel Passport)
- **Pipeline utilizzata**: ibrida (PDF vision + OCR), single-supplier
- **Credenziali**: fornite fuori banda. Le variabili da configurare sono `APP_NAME` e `APP_PASSWORD`. Non hardcodarle nel codice: leggile da variabili d'ambiente o file di configurazione.

Tutti i percorsi indicati di seguito sono relativi al base URL.

---

## 2. Flusso end-to-end

Il client deve eseguire questi passi, in ordine:

1. **Login** una sola volta → ottiene un `access_token`.
2. **Per ciascun PDF**: chiamare l'endpoint `POST /api/documents/classify-hybrid` passando il file e lo slug del fornitore.
3. **Parsare la risposta** e decidere l'esito:
   - documento riconosciuto come appartenente al fornitore + tipo identificato → salvare classificazione e campi estratti;
   - documento non appartenente al fornitore → marcare come "non pertinente";
   - documento del fornitore ma tipo `non_classificabile` → marcare come "fornitore OK, tipo sconosciuto".
4. **Gestire errori** (401 → re-login; 422/5xx → vedi sezione errori).
5. **Loggare** ogni esito su file/CSV/DB per audit successivo.

Diagramma logico (testuale):

```
[start] → login → token in memoria
   │
   ▼
 per ogni PDF:
   ├── POST /api/documents/classify-hybrid (file + supplier)
   │     ├── 200 → salva risultato strutturato
   │     ├── 401 → re-login → retry (max 1 volta per file)
   │     ├── 422 → log errore (validazione/pipeline) → file successivo
   │     └── 5xx → backoff esponenziale → retry (max 3) → poi log e prosegui
   │
[end]
```

---

## 3. Autenticazione

### 3.1 Login

**Endpoint**: `POST /api/auth/login`

**Headers**:
```
Content-Type: application/json
Accept: application/json
```

**Body**:
```json
{
  "app_name": "<APP_NAME>",
  "password": "<APP_PASSWORD>"
}
```

**Risposta 200**:
```json
{ "token": "eyJ0eXAiOiJKV1QiLCJhbGciOi..." }
```

**Risposta 401** (credenziali errate):
```json
{ "error": "Credenziali non valide" }
```

### 3.2 Uso del token

In tutte le chiamate successive includere l'header:
```
Authorization: Bearer <token>
Accept: application/json
```

### 3.3 Lifecycle del token

- Il token non ha una scadenza dichiarata nell'API. **Considerarlo riusabile** finché l'API non restituisce `401`.
- Se ricevi `401` su una chiamata di classificazione, **ripeti il login** e ritenta la chiamata **una sola volta** con il nuovo token. Se anche il secondo tentativo fallisce con 401, segnala l'errore di autenticazione e fermati (le credenziali sono probabilmente cambiate o revocate).
- **Non rifare il login per ogni file**: serializza il valore in memoria e riusalo.
- **Non loggare il token in chiaro**. Trattalo come segreto.

---

## 4. Endpoint di classificazione

**Endpoint**: `POST /api/documents/classify-hybrid`

Endpoint single-supplier: verifica che il PDF appartenga al fornitore indicato, classifica il tipo di documento contro la tassonomia configurata a database per quel fornitore, ed estrae i campi previsti per quel tipo.

### 4.1 Parametri della richiesta

Sono ammessi due modi di invio. **Scegliere uno e usarlo coerentemente**.

#### Modo A — multipart/form-data (consigliato per file su disco)

`Content-Type: multipart/form-data` (impostato automaticamente dal client HTTP). Campi:

| Campo | Tipo | Obbligatorio | Note |
|---|---|---|---|
| `file` | file | sì (se non si usa `file_base64`) | Solo PDF. Max 20 MB. |
| `supplier` | string | sì | Slug del fornitore (es. `msc-crociere`). Deve esistere a database. |

#### Modo B — application/json con file in base64

`Content-Type: application/json`. Campi:

| Campo | Tipo | Obbligatorio | Note |
|---|---|---|---|
| `file_base64` | string | sì (se non si usa `file`) | Contenuto del PDF codificato in base64 (senza prefisso `data:`). Max 20 MB decodificati. |
| `file_name` | string | sì se si usa `file_base64` | Nome del file con estensione `.pdf`. Max 255 char. |
| `supplier` | string | sì | Come sopra. |

### 4.2 Vincoli

- Solo PDF (`mimes:pdf`). Altri formati restituiscono `422`.
- Dimensione massima: **20 MB** per file (sia in multipart sia in base64 decodificato).
- Lo slug del fornitore deve esistere nella tabella `suppliers`. In caso contrario: `422` con messaggio `Il fornitore specificato non esiste`.
- Tempo di esecuzione tipico per file: **5–30 secondi** (dipende da dimensione PDF, qualità OCR, modello LLM). Impostare un **timeout HTTP client di almeno 120 secondi**.
- Il server limita internamente a 300 secondi di esecuzione per richiesta.

### 4.3 Esempio richiesta multipart (curl)

```bash
curl -X POST https://services.d74.cloud/api/documents/classify-hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -F "supplier=msc-crociere" \
  -F "file=@/path/al/documento.pdf"
```

### 4.4 Esempio richiesta JSON base64

```bash
curl -X POST https://services.d74.cloud/api/documents/classify-hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "supplier": "msc-crociere",
    "file_name": "documento.pdf",
    "file_base64": "JVBERi0xLjQK..."
  }'
```

---

## 5. Risposta dell'API

### 5.1 Schema della risposta di successo (HTTP 200)

```json
{
  "success": true,
  "data": {
    "supplier_verification": {
      "supplier": "msc-crociere",
      "belongs_to_supplier": true,
      "confidence": 0.95,
      "model": "google/gemini-3-flash-preview"
    },
    "classification": {
      "document_type": "biglietto_imbarco",
      "document_type_label": "Biglietto di imbarco",
      "confidence": 0.92,
      "model": "google/gemini-3-flash-preview"
    },
    "extracted_fields": {
      "numero_prenotazione": { "value": "ABC123456", "confidence": 0.99 },
      "data_partenza":       { "value": "2026-07-12", "confidence": 0.97 },
      "nome_passeggero":     { "value": "Mario Rossi", "confidence": 0.95 }
    },
    "pipeline": "hybrid",
    "metadata": {
      "classification_model": "google/gemini-3-flash-preview",
      "verification_model":   "google/gemini-3-flash-preview",
      "extraction_model":     "google/gemini-3-flash-preview",
      "ocr_engine": "paddleocr",
      "ocr_text_length": 2456,
      "ocr_pages": 3,
      "token_usage": { "prompt_tokens": 1234, "completion_tokens": 567, "total_tokens": 1801 },
      "input_mode": "multipart"
    }
  }
}
```

### 5.2 Significato dei campi

#### `supplier_verification`
- `supplier` (string): slug del fornitore verificato (riflette il parametro inviato).
- `belongs_to_supplier` (boolean): `true` se il sistema ritiene che il PDF appartenga al fornitore indicato.
- `confidence` (float, 0.0–1.0): livello di confidenza della verifica.
- `model` (string): modello LLM usato per la verifica.

#### `classification`
- `document_type` (string|null): chiave (slug) del tipo di documento. Esempi: `biglietto_imbarco`, `fattura`. Valore speciale `non_classificabile` quando il documento è del fornitore ma non rientra in nessun tipo configurato. `null` solo se la classificazione non è stata eseguita (es. `belongs_to_supplier=false`).
- `document_type_label` (string|null): nome leggibile del tipo di documento. `null` negli stessi casi del precedente.
- `confidence` (float|null): confidenza della classificazione.
- `model` (string|null): modello LLM usato.

#### `extracted_fields`
- `object | null`. Mappa `field_key → { value, confidence }`.
- `value`: stringa con il valore estratto (può essere data, numero, testo libero — sempre come stringa).
- `confidence`: float 0.0–1.0.
- È **`null`** in tutti questi casi:
  - `belongs_to_supplier = false`
  - `document_type` = `non_classificabile`
  - `document_type` = `null`
  - estrazione fallita (es. nessun campo configurato per quel tipo)
- L'insieme delle chiavi presenti dipende dal tipo di documento e dalla configurazione a database del fornitore. **Non assumere uno schema fisso**: itera dinamicamente sulle chiavi.

#### `pipeline`
- Stringa fissa `"hybrid"` per questo endpoint.

#### `metadata`
- `classification_model`, `verification_model`, `extraction_model`: modelli usati nei vari step.
- `ocr_engine`: motore OCR (`paddleocr`, `pdftotext`, o `null` se OCR fallito non bloccante).
- `ocr_text_length`: numero di caratteri estratti via OCR.
- `ocr_pages`: numero di pagine elaborate (può essere `null`).
- `token_usage`: consumo token LLM aggregato.
- `input_mode`: `"multipart"` o `"base64"`.

### 5.3 Casi particolari (HTTP 200, ma esito "negativo")

Una risposta `200` può comunque indicare che il documento non è stato classificato. Cinque scenari da gestire esplicitamente nel client:

| Scenario | `belongs_to_supplier` | `document_type` | `extracted_fields` | Azione consigliata |
|---|---|---|---|---|
| OK pieno | `true` | chiave valida (≠ `non_classificabile`) | oggetto | Salvare classificazione + campi |
| Tipo sconosciuto | `true` | `"non_classificabile"` | `null` | Salvare come "tipo sconosciuto", file da rivedere |
| Non del fornitore | `false` | `null` o `"non_classificabile"` | `null` | Marcare come "non pertinente" |
| Confidenza bassa | `true` | chiave valida ma `classification.confidence < 0.7` | oggetto | Salvare ma flaggare per revisione manuale |
| Estrazione vuota | `true` | chiave valida | `{}` o `null` | Salvare classificazione, segnalare campi mancanti |

**Soglia di confidenza consigliata**: trattare come "alta confidenza" valori ≥ 0.85, "media" 0.7–0.85, "bassa" < 0.7. La soglia è una scelta del client, non un vincolo del server.

---

## 6. Gestione errori

Tutte le risposte di errore hanno questa forma:

```json
{
  "success": false,
  "error": {
    "code": "...",
    "message": "..."
  }
}
```

(Eccezione: errori 401 di autenticazione che restituiscono `{"error": "..."}` o `{"message": "Unauthenticated."}` — il client deve gestire entrambi.)

### 6.1 Tabella errori

| HTTP | `error.code` (quando presente) | Causa | Strategia client |
|---|---|---|---|
| 401 | — | Token mancante, scaduto, revocato | Re-login (1 retry per file), poi fallisci |
| 422 | `INVALID_BASE64` | `file_base64` non decodificabile | Bug nel client: log e salta file |
| 422 | `FILE_TOO_LARGE` | File > 20 MB | Log, segnala il file come "oversize", salta |
| 422 | (errori di validazione Laravel) | Mime non PDF, campo mancante, slug fornitore inesistente | Verifica payload; se ricorrente, abortire il batch |
| 422 | codice specifico della pipeline (`OCR_FAILED`, `CLASSIFICATION_FAILED`, ecc.) | Errore nella pipeline di classificazione | Log, salta il file, prosegui col successivo |
| 429 | — | Rate limit (se applicato a livello infrastruttura) | Backoff esponenziale e retry |
| 500 | `CONFIG_ERROR` | Errore di configurazione lato server | Log e segnala: non risolvibile dal client |
| 500 | `INTERNAL_ERROR` | Eccezione non gestita | Backoff e retry fino a 3 volte; poi log e prosegui |
| 502/503/504 | — | Server temporaneamente non raggiungibile | Backoff esponenziale e retry |

### 6.2 Backoff esponenziale (per 5xx e timeout)

Schema consigliato:
- tentativo 1 → attesa 2 s
- tentativo 2 → attesa 5 s
- tentativo 3 → attesa 15 s
- dopo il terzo fallimento: logga l'errore, marca il file come "fallito" e prosegui col successivo.

Non applicare retry agli errori `422`: sono deterministici, ritentare la stessa richiesta produrrà lo stesso errore.

### 6.3 Errori di rete / timeout

- Imposta timeout HTTP almeno a **120 secondi** per richiesta.
- In caso di timeout o errore di connessione, applica la stessa strategia di backoff dei 5xx.

---

## 7. Considerazioni per l'elaborazione batch

### 7.1 Concorrenza

L'API non documenta limiti hard di concorrenza, ma:
- ogni richiesta è onerosa lato server (OCR + LLM);
- consiglio: **massimo 3–5 richieste in parallelo** in produzione;
- per test e debug iniziale: **serial (1 alla volta)** per leggere log e tempi.

### 7.2 Idempotenza

Le richieste **non sono idempotenti**: ritentare la stessa classificazione consuma token e tempo. Implementare una **cache lato client** (es. hash SHA-256 del PDF → risultato già ottenuto) per evitare ri-elaborazioni su file già processati.

### 7.3 Logging consigliato

Per ogni file processato, registrare almeno:
- nome file
- hash del file (per dedup)
- timestamp inizio/fine
- esito (HTTP status + `success`)
- `supplier_verification.belongs_to_supplier` + confidence
- `classification.document_type` + confidence
- numero di campi estratti
- in caso di errore: `error.code` e `error.message`

Formato consigliato: CSV o JSONL, una riga per file.

### 7.4 Output strutturato consigliato

Il client dovrebbe produrre, per ogni file, un record con questa forma minima:

```json
{
  "source_file": "documento.pdf",
  "file_hash": "sha256:...",
  "processed_at": "2026-05-20T10:32:11Z",
  "status": "classified | not_supplier | unknown_type | error",
  "supplier": "msc-crociere",
  "supplier_match": true,
  "document_type": "biglietto_imbarco",
  "document_type_label": "Biglietto di imbarco",
  "classification_confidence": 0.92,
  "extracted_fields": { "...": "..." },
  "error_code": null,
  "error_message": null
}
```

dove `status` è derivato dalla tabella in §5.3.

---

## 8. Esempio completo in Python

Pseudocodice indicativo (richiede `requests`):

```python
import os
import time
import hashlib
import requests

BASE_URL = "https://services.d74.cloud"
APP_NAME = os.environ["APP_NAME"]
APP_PASSWORD = os.environ["APP_PASSWORD"]
SUPPLIER_SLUG = os.environ["SUPPLIER_SLUG"]  # es. "msc-crociere"
TIMEOUT = 120


def login() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"app_name": APP_NAME, "password": APP_PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def classify(token: str, pdf_path: str) -> tuple[int, dict]:
    with open(pdf_path, "rb") as fh:
        r = requests.post(
            f"{BASE_URL}/api/documents/classify-hybrid",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            data={"supplier": SUPPLIER_SLUG},
            files={"file": (os.path.basename(pdf_path), fh, "application/pdf")},
            timeout=TIMEOUT,
        )
    return r.status_code, r.json()


def derive_status(payload: dict) -> str:
    data = payload["data"]
    if not data["supplier_verification"]["belongs_to_supplier"]:
        return "not_supplier"
    dt = data["classification"]["document_type"]
    if dt is None or dt == "non_classificabile":
        return "unknown_type"
    return "classified"


def process(pdf_path: str, token_holder: list) -> dict:
    file_hash = hashlib.sha256(open(pdf_path, "rb").read()).hexdigest()
    delays = [2, 5, 15]
    attempt = 0
    while True:
        try:
            status, payload = classify(token_holder[0], pdf_path)
        except requests.RequestException as e:
            if attempt >= len(delays):
                return {"source_file": pdf_path, "status": "error",
                        "error_code": "NETWORK", "error_message": str(e)}
            time.sleep(delays[attempt]); attempt += 1; continue

        if status == 200 and payload.get("success"):
            data = payload["data"]
            return {
                "source_file": pdf_path,
                "file_hash": file_hash,
                "status": derive_status(payload),
                "supplier": SUPPLIER_SLUG,
                "supplier_match": data["supplier_verification"]["belongs_to_supplier"],
                "document_type": data["classification"]["document_type"],
                "document_type_label": data["classification"]["document_type_label"],
                "classification_confidence": data["classification"]["confidence"],
                "extracted_fields": data["extracted_fields"],
                "error_code": None,
                "error_message": None,
            }

        if status == 401:
            # re-login una sola volta
            if attempt > 0:
                return {"source_file": pdf_path, "status": "error",
                        "error_code": "AUTH", "error_message": "re-login fallito"}
            token_holder[0] = login()
            attempt = 1
            continue

        if status == 422:
            err = payload.get("error", {})
            return {"source_file": pdf_path, "status": "error",
                    "error_code": err.get("code"), "error_message": err.get("message")}

        if 500 <= status < 600 or status == 429:
            if attempt >= len(delays):
                err = payload.get("error", {}) if isinstance(payload, dict) else {}
                return {"source_file": pdf_path, "status": "error",
                        "error_code": err.get("code", f"HTTP_{status}"),
                        "error_message": err.get("message", "server error")}
            time.sleep(delays[attempt]); attempt += 1; continue

        return {"source_file": pdf_path, "status": "error",
                "error_code": f"HTTP_{status}", "error_message": str(payload)}


def main(pdf_files: list[str]) -> list[dict]:
    token_holder = [login()]
    return [process(p, token_holder) for p in pdf_files]
```

Note implementative:
- la lista `token_holder` serve a passare il token "per riferimento" e poterlo aggiornare dopo un re-login;
- per concorrenza: sostituire `[process(p, token_holder) for p in pdf_files]` con un `ThreadPoolExecutor(max_workers=3)`;
- il calcolo dell'hash è duplicato nel codice di esempio (rileggi il file) — in produzione calcolarlo una sola volta.

---

## 9. Checklist di verifica del client

Prima di considerare il client pronto, verificare che:

- [ ] Le credenziali siano lette da variabili d'ambiente, non hardcodate.
- [ ] Il token venga riusato tra chiamate e rinnovato solo su 401.
- [ ] Il timeout HTTP sia ≥ 120 s.
- [ ] I file > 20 MB siano filtrati prima dell'invio (per evitare richieste destinate a fallire).
- [ ] Solo file PDF siano inviati (no JPG/PNG/altri).
- [ ] Il client gestisca **tutti e cinque** gli scenari di esito descritti in §5.3.
- [ ] Errori 422 non vengano ritentati.
- [ ] Errori 5xx/timeout abbiano backoff esponenziale con tetto a 3 retry.
- [ ] Ogni esito sia loggato in modo strutturato (CSV/JSONL).
- [ ] Sia implementata una deduplica per hash file per evitare ri-elaborazioni.
- [ ] Concorrenza limitata a 3–5 richieste parallele al massimo.

---

## 10. Riferimenti rapidi

| Cosa | Valore |
|---|---|
| Base URL prod | `https://services.d74.cloud` |
| Login | `POST /api/auth/login` |
| Classificazione | `POST /api/documents/classify-hybrid` |
| Auth header | `Authorization: Bearer <token>` |
| Max file size | 20 MB |
| Mime ammessi | `application/pdf` |
| Timeout consigliato | 120 s |
| Parallelismo consigliato | 3–5 richieste |
