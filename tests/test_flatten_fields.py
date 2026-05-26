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
