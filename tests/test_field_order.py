"""Le colonne dinamiche seguono un ordine preferito (commissioni e provvigioni
adiacenti), con i campi non previsti aggiunti in fondo in ordine alfabetico."""
from excel_writer import collect_field_columns


def test_ordine_preferito_commissioni_e_provvigioni_adiacenti():
    records = [{"campi": {
        "totale": "1", "provvigioni": "2", "data_documento": "3",
        "commissioni": "4", "numero_documento": "5",
    }}]
    cols = collect_field_columns(records)
    assert cols == ["data_documento", "numero_documento", "totale", "commissioni", "provvigioni"]
    # commissioni e provvigioni sono una accanto all'altra
    assert cols.index("provvigioni") - cols.index("commissioni") == 1


def test_campi_non_previsti_vanno_in_fondo_ordinati():
    records = [{"campi": {"zeta": "1", "totale": "2", "alfa": "3", "commissioni": "4"}}]
    cols = collect_field_columns(records)
    assert cols == ["totale", "commissioni", "alfa", "zeta"]
