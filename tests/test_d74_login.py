from unittest.mock import MagicMock
from d74_client import D74Client

def _resp(status, json_data):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m

def test_login_salva_e_ritorna_il_token():
    session = MagicMock()
    session.post.return_value = _resp(200, {"token": "tok-123"})
    client = D74Client("https://x", "app", "pwd", "slug", session=session)

    token = client.login()

    assert token == "tok-123"
    assert client.token == "tok-123"
    args, kwargs = session.post.call_args
    assert args[0] == "https://x/api/auth/login"
    assert kwargs["json"] == {"app_name": "app", "password": "pwd"}
