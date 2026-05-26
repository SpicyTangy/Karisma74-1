# Template estrazione email + PDF da Gmail

File unico autoportante per estrarre email e allegati PDF da Gmail via IMAP +
OAuth2. Riusa la plumbing del progetto MSC senza dipendere da `utils/`.

## Setup (3 passi)

1. **Credenziali** — copia `.env.example` in `.env` e incolla i valori OAuth2.
   Usando lo **stesso account** (`automazione.74srl`), sono gli stessi
   `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` già in uso.

2. **Dipendenze**
   ```
   pip install -r requirements.txt
   ```

3. **Avvio**
   ```
   python email_extractor_template.py --from 2026-01-01 --to 2026-05-31
   ```
   Senza `--from`/`--to` usa gli ultimi 30 giorni.

## L'UNICA cosa da personalizzare

In cima a `email_extractor_template.py`, la costante:

```python
SEARCH_QUERY = "from:bookingrdv has:attachment"
```

Usa la sintassi di ricerca di Gmail (`from:`, `subject:`, `has:attachment`,
`OR`, …). Le date `after:`/`before:` le aggiunge il codice in automatico — non
metterle qui.

## Output

```
output/
├── email_YYYYMMDD.xlsx        ← una riga per PDF (data, mittente, oggetto, file)
└── pdf/<anno>/<mese>/         ← allegati PDF, prefissati con la data
```

## Cosa NON c'è (di proposito)

Rispetto a `gmail_extractor.py` del progetto MSC, qui è stata tolta la parte di
classificazione (d74-service), i marker estratto conto e il dedup per numero
pratica. È un estrattore "grezzo": tira giù email + PDF e fa l'Excel. Se in
futuro serve la classificazione, si aggancia come nel file MSC.
