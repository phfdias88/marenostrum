"""
Testes de autenticacao.

Foco: garantir que NENHUMA forma de fraude ou ambiguidade no login devolve
JWT. Mensagens de erro genericas (anti user-enumeration) sao verificadas.
"""
from app.core.security import create_access_token


# --------------------------------------------------------------------- /login


def test_login_success_returns_token_with_tenant_id(client, tenant_a):
    tenant, user, _ = tenant_a
    r = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "alpha",
            "email": "alpha@example.com",
            "password": "Senha@Forte123",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user_id"] == str(user.id)
    assert body["tenant_id"] == str(tenant.id)
    assert body["role"] == "owner"


def test_login_wrong_password_returns_401_generic(client, tenant_a):
    r = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "alpha",
            "email": "alpha@example.com",
            "password": "errada",
        },
    )
    assert r.status_code == 401
    # Mensagem generica — NAO revela se foi senha ou usuario
    assert r.json()["message"] == "Credenciais invalidas"


def test_login_unknown_email_returns_401_generic(client, tenant_a):
    r = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "alpha",
            "email": "naoexiste@example.com",
            "password": "Senha@Forte123",
        },
    )
    assert r.status_code == 401
    assert r.json()["message"] == "Credenciais invalidas"


def test_login_unknown_tenant_returns_401_generic(client, tenant_a):
    r = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "nao-existe",
            "email": "alpha@example.com",
            "password": "Senha@Forte123",
        },
    )
    assert r.status_code == 401
    assert r.json()["message"] == "Credenciais invalidas"


def test_login_user_from_other_tenant_returns_401(client, tenant_a, tenant_b):
    """
    Bug catastrofico: usuario do tenant A logando com slug do tenant B.
    DEVE recusar (sem revelar que o email existe noutro lugar).
    """
    r = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "bravo",  # tenant errado
            "email": "alpha@example.com",  # email do tenant A
            "password": "Senha@Forte123",
        },
    )
    assert r.status_code == 401


# --------------------------------------------------------------------- /me


def test_me_without_token_returns_401(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_with_token_returns_user_and_tenant(auth_a, tenant_a):
    tenant, user, _ = tenant_a
    r = auth_a.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == str(user.id)
    assert body["tenant_id"] == str(tenant.id)
    assert body["tenant_slug"] == "alpha"
    assert body["tenant_name"] == "Campanha Alpha"
    assert body["email"] == "alpha@example.com"
    assert body["role"] == "owner"


def test_me_with_garbage_token_returns_401(client):
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer this-is-not-a-jwt"},
    )
    assert r.status_code == 401


def test_me_with_forged_token_other_tenant_returns_401(
    client, tenant_a, db_session
):
    """
    Token assinado corretamente, mas o `tid` aponta pra um tenant onde
    o `sub` NAO existe. Deve recusar (defesa: get_with_tenant em /me).
    """
    _, user_a, _ = tenant_a
    # Forja: pega user_id do A, mas troca tenant_id por um UUID inexistente
    from uuid import uuid4
    fake_tenant_id = uuid4()
    forged = create_access_token(
        user_id=user_a.id,
        tenant_id=fake_tenant_id,
        role="owner",
    )
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert r.status_code == 401


def test_me_inactive_user_returns_401(client, db_session, tenant_a):
    """Usuario foi desativado apos receber token — token nao serve mais."""
    _, user, token = tenant_a
    user.is_active = False
    db_session.commit()

    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401
