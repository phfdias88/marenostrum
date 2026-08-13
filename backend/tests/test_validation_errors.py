"""
Handler de erros de validação (422) — mensagens PT-BR claras.

Regressão do relato do sócio (jul/2026): trocar senha com uma senha curta
mostrava "Erro no servidor (HTTP 422)" (parecia bug do sistema) em vez do
requisito real. O handler agora devolve {code, message} amigável — e NUNCA
ecoa o valor digitado (o 422 padrão do FastAPI vazava a senha em "input").
"""
from app.core.security import create_access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_change_password_short_returns_friendly_message(client, tenant_a):
    _, _, token = tenant_a
    r = client.post(
        "/api/v1/auth/change-password",
        headers=_auth(token),
        json={"current_password": "qualquer", "new_password": "123"},
    )
    assert r.status_code == 422
    body = r.json()
    # Formato consistente {code, message} — o frontend lê `message`.
    assert body["code"] == "validation_error"
    assert "10 caracteres" in body["message"]
    # NÃO vaza o valor digitado (o 422 cru do FastAPI traria "input":"123").
    assert "123" not in str(body)
    assert "input" not in body


def test_missing_field_returns_friendly_message(client, tenant_a):
    _, _, token = tenant_a
    r = client.post(
        "/api/v1/auth/change-password",
        headers=_auth(token),
        json={"current_password": "qualquer"},  # falta new_password
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert body["message"]  # não-vazio
    assert "HTTP 422" not in body["message"]


def test_weak_password_denylist_message(client, tenant_a):
    _, _, token = tenant_a
    # >= 10 chars mas na denylist → validador custom (value_error) → msg PT.
    r = client.post(
        "/api/v1/auth/change-password",
        headers=_auth(token),
        json={"current_password": "qualquer", "new_password": "senha123456"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    # Mensagem do validador (sem o prefixo "Value error," do Pydantic).
    assert "Value error" not in body["message"]
    assert body["message"].lower().startswith("essa senha")
