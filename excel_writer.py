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
