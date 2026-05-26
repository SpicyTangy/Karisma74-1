from gmail_fetch import _safe_filename


def test_rimuove_ritorni_a_capo():
    # caso reale: header MIME ripiegato → \r\n nel nome (crashava su Windows)
    assert _safe_filename("MEMORANDUM DI\r\n PAGAMENTO_N_26.pdf") == "MEMORANDUM DI PAGAMENTO_N_26.pdf"


def test_sostituisce_caratteri_non_validi():
    assert _safe_filename("fat:tura?2026*.pdf") == "fat_tura_2026_.pdf"


def test_collassa_spazi_e_taglia_i_bordi():
    assert _safe_filename("   doc   2026 .pdf  ") == "doc 2026 .pdf"


def test_nome_vuoto_ritorna_default():
    assert _safe_filename("   \r\n  ") == "allegato.pdf"
