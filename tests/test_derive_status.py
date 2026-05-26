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
