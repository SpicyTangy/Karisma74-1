# Estrattore email + classificatore documenti (Karisma) — Design

**Data:** 2026-05-26
**Stato:** approvato (design), in attesa di implementazione

## Obiettivo

Scaricare i PDF allegati alle email di un fornitore da una casella Gmail e, per
ciascun PDF, ottenere classificazione del tipo di documento e campi estratti
chiamando l'API d74-service (`classify-hybrid`). Produrre un Excel di riepilogo.

Riusa la metà "fetch da Gmail" del template del collega (progetto MSC) e
riaggancia la classificazione d74-service che il template aveva volutamente
rimosso. Il flusso completo equivale a quello che il collega aveva per MSC, ma
per un fornitore diverso.

## Contesto / fonti

- **Template del collega** (`templates/email_extractor_template.py` + guide):
  login OAuth2/IMAP a Gmail, ricerca per mittente/data, download PDF, Excel di
  metadati. È un estrattore "grezzo" — senza classificazione.
- **Specifica API** (`templates/integrazione-classify-hybrid (1).md`): client per
  `POST /api/documents/classify-hybrid` di d74-service, con login OAuth2 Bearer,
  schema risposta, gestione errori e pseudocodice Python.

## Approccio scelto

**Due fasi distinte, più moduli in un'unica cartella** (approccio A):
- `download` e `classify` lanciabili separatamente o insieme (`all`).
- Tenere le fasi separate perché la classificazione costa tempo (5–30 s/file) e
  token LLM, **non è idempotente**, e il MD consiglia di partire serial e
  ispezionare ciò che si scarica prima di classificare.

## Struttura dei file

```
karisma/
├── tool.py            ← CLI: comandi download / classify / all, logging, cache hash
├── gmail_fetch.py     ← fetch email + download PDF (dal template del collega)
├── d74_client.py      ← login + classify-hybrid, retry/backoff, gestione errori
├── excel_writer.py    ← scrittura Excel con colonne dinamiche
├── requirements.txt   ← openpyxl, python-dotenv, google-auth, google-auth-oauthlib, requests
├── .env               ← credenziali (MAI su git)
├── .gitignore         ← .env, output/
└── output/            ← pdf/ + Excel + log (gitignored)
```

## Componenti e responsabilità

### `tool.py` — orchestratore CLI
- Comandi: `download --from YYYY-MM-DD --to YYYY-MM-DD`, `classify`, `all`.
- Carica `.env`, configura il logging.
- **Cache anti-spreco**: hash SHA-256 del PDF → risultato già ottenuto (file
  `output/cache.json`). In fase `classify`, un file già in cache non viene
  rinviato all'API.
- Filtra prima dell'invio i file > 20 MB e non-PDF.
- Opzione `--workers N` (default 1, max 5) per la concorrenza; default serial in
  fase di rodaggio.

### `gmail_fetch.py` — fetch da Gmail
- Riuso del template: `_get_access_token` (OAuth2 → XOAUTH2), `fetch_emails`
  (ricerca `X-GM-RAW` con `SEARCH_QUERY` + `after:`/`before:`), `download_pdfs`
  (salva in `output/pdf/<anno>/<mese>/<data>_<nomefile>.pdf`).
- `SEARCH_QUERY` del fornitore configurabile (costante in cima al modulo o env).
- Sola lettura sulla casella: non cancella né sposta nulla.

### `d74_client.py` — client API d74-service
- `login() -> str`: `POST /api/auth/login` con `app_name`/`password` da env,
  ritorna il token. Token riusato in memoria, rinnovato solo su 401.
- `classify(token, pdf_path) -> (status_code, payload)`: `POST
  /api/documents/classify-hybrid` multipart con `supplier` + `file`,
  timeout 120 s.
- Gestione errori secondo MD §6:
  - 401 → re-login una sola volta, poi fallisci.
  - 422 → log e salta (nessun retry: deterministico).
  - 5xx / 429 / timeout / errore rete → backoff 2 s / 5 s / 15 s, max 3 retry.
- `derive_status(payload) -> str`: mappa gli scenari §5.3 in uno stato:
  `classificato`, `non_pertinente`, `tipo_sconosciuto`, `bassa_confidenza`
  (classif. confidence < 0.7), `errore`.

### `excel_writer.py` — Excel
- Foglio unico `Risultati`.
- **Colonne fisse**: `file`, `data_email`, `mittente`, `oggetto`, `status`,
  `fornitore_ok`, `tipo_documento`, `tipo_label`, `confidenza_classif`,
  `errore`.
- **Colonne dinamiche**: una per ogni `field_key` estratto, costruite come
  unione di tutte le chiavi viste tra i documenti (lo schema dei campi dipende
  dal tipo di documento — il MD dice esplicitamente di non assumere uno schema
  fisso). Valore = `extracted_fields[key].value`.
- Output: `output/risultati_YYYYMMDD.xlsx`.

## Flusso dati

```
download:  Gmail ──> output/pdf/<anno>/<mese>/*.pdf
classify:  scandisce output/pdf/**/*.pdf
             └─ per ogni PDF: hash ──> in cache? ──sì─> riusa risultato
                                          └──no──> POST /classify-hybrid
                                                    └─> salva in cache + accumula riga
           ──> excel_writer ──> output/risultati_YYYYMMDD.xlsx
all:       download, poi classify, in sequenza.
```

## Configurazione (`.env`)

Esistenti (riusati dal template):
`GMAIL_USER`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`.

Nuovi (per l'API d74):
`APP_NAME`, `APP_PASSWORD`, `SUPPLIER_SLUG`.

Da rimuovere: `GMAIL_ACCOUNT_PASSWORD` (non usata — lo script si autentica solo
via OAuth2).

Opzionale: `D74_BASE_URL` (default `https://services.d74.cloud`).

## Testing

TDD sulla logica pura, senza rete:
- `derive_status`: i 5 scenari della tabella §5.3 (+ bassa confidenza).
- `excel_writer`: costruzione colonne dinamiche da chiavi eterogenee, gestione
  `extracted_fields = null`.
- `d74_client`: logica di retry/backoff e re-login con `requests` mockato.
- Costruzione query Gmail (`after:`/`before:` da `--from`/`--to`).

La parte IMAP/HTTP reale si verifica manualmente con le credenziali alla fine
(prima serial, leggendo i log).

## Sicurezza

- Credenziali solo in `.env`, mai nel codice né su git (`.gitignore`).
- Token API trattato come segreto: mai loggato in chiaro.
- Sola lettura sulla casella Gmail.

## Fuori scope (YAGNI)

- Caricamento dei dati su DB/gestionale/altra API (per ora solo Excel).
- Interfaccia grafica.
- Scheduling automatico (per ora lancio manuale).
