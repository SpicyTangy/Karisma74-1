"""Robustezza: se il file Excel è bloccato (aperto in Excel) si ripiega su un
nome alternativo con l'orario invece di crashare."""
import re

from excel_writer import _save_workbook, _timestamped_path, write_excel


def test_timestamped_path_inserisce_orario():
    alt = _timestamped_path("output/risultati_20260526.xlsx")
    # es. output/risultati_20260526_143700.xlsx
    assert re.search(r"risultati_20260526_\d{6}\.xlsx$", alt.replace("\\", "/"))


class FakeWorkbook:
    def __init__(self, locked_paths=()):
        self.locked = set(locked_paths)
        self.saved = []

    def save(self, path):
        if path in self.locked:
            raise PermissionError(13, "file aperto altrove")
        self.saved.append(path)


def test_save_workbook_percorso_normale():
    wb = FakeWorkbook()
    assert _save_workbook(wb, "ris.xlsx") == "ris.xlsx"
    assert wb.saved == ["ris.xlsx"]


def test_save_workbook_ripiega_se_bloccato():
    wb = FakeWorkbook(locked_paths=["ris.xlsx"])
    out = _save_workbook(wb, "ris.xlsx")
    assert out != "ris.xlsx"
    assert re.search(r"ris_\d{6}\.xlsx$", out.replace("\\", "/"))
    assert wb.saved == [out]            # ha salvato sul nome alternativo


def test_write_excel_ritorna_il_path(tmp_path):
    out = write_excel([{"file": "a.pdf", "campi": {}}], str(tmp_path / "r.xlsx"))
    assert out == str(tmp_path / "r.xlsx")
