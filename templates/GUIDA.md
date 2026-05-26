# Estrattore email + PDF da Gmail — Guida completa

Script per scaricare email e relativi allegati PDF da Gmail, in locale, e
produrre un Excel di riepilogo. Niente servizi esterni: gira tutto sul tuo PC.

Questa guida copre **tutto**: cosa hai ricevuto, setup passo-passo, come
personalizzarlo, output e cosa fare se qualcosa non parte.

---

## 1. Cosa hai ricevuto

```
templates/
├── email_extractor_template.py   ← lo script (file unico, niente altro da scaricare)
├── .env.example                  ← modello per le credenziali (vuoto)
├── requirements.txt              ← dipendenze da installare
├── README.md                     ← versione breve di questa guida
└── GUIDA.md                      ← questa guida
```

**Le credenziali NON sono in questi file.** Te le passo a parte (di persona o
canale sicuro): sono 4 valori che incollerai nel `.env` al passo 3.

---

## 2. Prerequisiti

- **Python 3.10 o superiore** installato.
  Verifica con:
  ```
  python --version
  ```
  Se non ce l'hai: https://www.python.org/downloads/ (in installazione spunta
  "Add Python to PATH").

---

## 3. Setup passo-passo (~5 minuti)

### Passo 1 — Metti la cartella dove vuoi
Scompatta/copia la cartella `templates/` in una posizione comoda (es.
`Documenti\estrattore-email\`). Apri lì un terminale (PowerShell).

### Passo 2 — Installa le dipendenze
```
pip install -r requirements.txt
```
Installa solo 4 librerie: `openpyxl`, `python-dotenv`, `google-auth`,
`google-auth-oauthlib`.

### Passo 3 — Crea il file `.env` con le credenziali
1. Copia `.env.example` e rinomina la copia in `.env` (senza estensione, solo
   `.env`).
2. Apri `.env` con un editor di testo e incolla i 4 valori che ti ho passato:
   ```
   GMAIL_USER=automazione.74srl@gmail.com
   GMAIL_CLIENT_ID=...
   GMAIL_CLIENT_SECRET=...
   GMAIL_REFRESH_TOKEN=...
   ```
3. Salva. **Non condividere mai questo file** e non metterlo su Git.

### Passo 4 — Imposta cosa cercare (l'unica vera personalizzazione)
Apri `email_extractor_template.py` e trova in alto questa riga:
```python
SEARCH_QUERY = "from:bookingrdv has:attachment"
```
Modificala in base alle TUE email. Usa la sintassi di ricerca di Gmail (la
stessa che useresti nella barra di ricerca di Gmail). Vedi gli esempi al
punto 5.
> ⚠️ Non scrivere le date qui: `after:`/`before:` le aggiunge lo script da solo
> in base a `--from`/`--to`.

### Passo 5 — Avvia
```
python email_extractor_template.py --from 2026-01-01 --to 2026-05-31
```
Se ometti `--from`/`--to`, usa automaticamente **gli ultimi 30 giorni**.

---

## 4. Output

Al termine trovi tutto nella cartella `output/`:

```
output/
├── email_YYYYMMDD.xlsx        ← una riga per ogni PDF trovato
└── pdf/
    └── <anno>/<mese>/         ← i PDF scaricati, col prefisso data nel nome
```

L'Excel ha 4 colonne: `data_email`, `mittente`, `oggetto`, `pdf_file`.

---

## 5. Esempi di `SEARCH_QUERY`

Scegli quello che corrisponde alle tue email (puoi combinarli):

| Obiettivo | `SEARCH_QUERY` |
|---|---|
| Da un mittente preciso, con allegato | `from:bookingrdv has:attachment` |
| Da un intero dominio | `from:raccontidiviaggio.it has:attachment` |
| Filtra anche per oggetto | `from:bookingrdv subject:conferma has:attachment` |
| Più mittenti insieme (OR) | `(from:tizio.it OR from:caio.it) has:attachment` |
| Parola chiave ovunque nell'email | `"estratto conto" has:attachment` |
| Solo PDF (allegato generico) | `has:attachment filename:pdf` |
| Partenza "larga" se non sai il mittente | `has:attachment` |

**Consiglio:** se non sei sicuro di come appaiono le tue email, parti largo
(`has:attachment`), guarda cosa scarica, poi stringi aggiungendo `from:` o
`subject:`.

---

## 6. Se qualcosa non funziona

| Sintomo | Causa probabile / cosa fare |
|---|---|
| `Variabile GMAIL_... mancante nel file .env` | Il `.env` non esiste o è incompleto. Rivedi il Passo 3. |
| `Autenticazione IMAP fallita` | Credenziali OAuth2 errate o refresh token scaduto. Richiedimele aggiornate. |
| `Email trovate: 0` | La `SEARCH_QUERY` non matcha nulla nel periodo scelto. Allarga le date o semplifica la query (parti da `has:attachment`). |
| `python` non riconosciuto | Python non installato o non nel PATH. Vedi punto 2. |
| Nessun PDF scaricato ma email trovate | Le email matchate non hanno allegati PDF (magari altri formati). Verifica la query. |

---

## 7. Note

- Lo script è in **sola lettura** sulla casella: scarica, non cancella né sposta
  nulla su Gmail.
- È volutamente "grezzo": tira giù email + PDF e fa l'Excel. Non classifica i
  documenti. Se in futuro ti serve anche la classificazione, fammi sapere.
- Domande? Scrivimi.
