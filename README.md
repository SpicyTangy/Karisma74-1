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
