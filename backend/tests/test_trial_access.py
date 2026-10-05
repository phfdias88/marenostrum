"""
Acesso temporário (trial) — conta de teste/demonstração com tempo limitado.

Regras (pedido do PO):
- usage_limit_hours define o tempo; o relógio SÓ começa no 1º login.
- A partir do 1º login corre absoluto até expires_at.
- Login após expirar → 403 com código "trial_expired".
- O JWT emitido NUNCA vive além de expires_at.
"""
from datetime import datetime, timedelta, timezone

from app.core.security import create_access_token, decode_access_token
from app.models.user import User


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _superadmin_token(db_session, tenant_a):
    """Definir prazo de acesso é exclusivo da Mare Nostrum (RBAC): os testes de
    trial promovem o owner do fixture a superadmin antes de criar a conta."""
    tenant, user, _ = tenant_a
    user.is_superadmin = True
    db_session.commit()
    return create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role.value,
    )


def _create_trial_user(client, owner_token, hours, email="trial@example.com"):
    r = client.post(
        "/api/v1/auth/users",
        headers=_auth(owner_token),
        json={
            "email": email,
            "full_name": "Usuário Trial",
            "role": "staff",
            "usage_limit_hours": hours,
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()  # tem temp_password


def test_create_stores_limit_and_zero_means_unlimited(client, tenant_a, db_session):
    owner_token = _superadmin_token(db_session, tenant_a)
    _create_trial_user(client, owner_token, 2.5, email="t25@example.com")
    u = db_session.query(User).filter(User.email == "t25@example.com").one()
    assert u.usage_limit_hours == 2.5
    assert u.first_login_at is None  # relógio ainda não começou

    # 0 = ilimitado → guarda NULL.
    _create_trial_user(client, owner_token, 0, email="unlimited@example.com")
    u2 = db_session.query(User).filter(User.email == "unlimited@example.com").one()
    assert u2.usage_limit_hours is None


def test_first_login_starts_clock_and_caps_jwt(client, tenant_a, db_session):
    tenant = tenant_a[0]
    owner_token = _superadmin_token(db_session, tenant_a)
    created = _create_trial_user(client, owner_token, 2, email="clock@example.com")

    r = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": "clock@example.com",
              "password": created["temp_password"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    u = db_session.query(User).filter(User.email == "clock@example.com").one()
    assert u.first_login_at is not None  # relógio iniciou AGORA
    assert u.expires_at is not None
    # expires_at ≈ first_login_at + 2h
    delta = (u.expires_at - u.first_login_at).total_seconds()
    assert abs(delta - 2 * 3600) < 5

    # O JWT NÃO vive além de expires_at (teto absoluto).
    exp = u.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    payload = decode_access_token(data["access_token"])
    assert payload.exp <= int(exp.timestamp())
    # E o expires_in do cookie reflete ~2h (não os 7 dias padrão).
    assert data["expires_in"] <= 2 * 3600 + 5


def test_expired_trial_blocks_login(client, tenant_a, db_session):
    tenant = tenant_a[0]
    owner_token = _superadmin_token(db_session, tenant_a)
    created = _create_trial_user(client, owner_token, 2, email="expired@example.com")
    # Simula trial já iniciado E vencido (relógio no passado).
    u = db_session.query(User).filter(User.email == "expired@example.com").one()
    now = datetime.now(timezone.utc)
    u.first_login_at = now - timedelta(hours=3)
    u.expires_at = now - timedelta(hours=1)
    db_session.commit()

    r = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": "expired@example.com",
              "password": created["temp_password"]},
    )
    assert r.status_code == 403
    body = r.json()
    assert body["code"] == "trial_expired"
    assert body["message"] == "Seu período de uso expirou."


def test_unlimited_user_gets_full_ttl(client, tenant_a, db_session):
    tenant = tenant_a[0]
    owner_token = _superadmin_token(db_session, tenant_a)
    created = _create_trial_user(client, owner_token, 0, email="full@example.com")
    r = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": "full@example.com",
              "password": created["temp_password"]},
    )
    assert r.status_code == 200
    # Sem trial → TTL padrão (muito maior que 2h).
    assert r.json()["expires_in"] > 24 * 3600
    u = db_session.query(User).filter(User.email == "full@example.com").one()
    assert u.first_login_at is None
    assert u.expires_at is None


def test_second_login_does_not_reset_clock(client, tenant_a, db_session):
    tenant = tenant_a[0]
    owner_token = _superadmin_token(db_session, tenant_a)
    created = _create_trial_user(client, owner_token, 5, email="twice@example.com")
    login = {"tenant_slug": tenant.slug, "email": "twice@example.com",
             "password": created["temp_password"]}

    client.post("/api/v1/auth/login", json=login)
    u = db_session.query(User).filter(User.email == "twice@example.com").one()
    first = u.first_login_at
    exp = u.expires_at

    # 2º login: NÃO reinicia o relógio (expira no mesmo instante absoluto).
    client.post("/api/v1/auth/login", json=login)
    db_session.refresh(u)
    assert u.first_login_at == first
    assert u.expires_at == exp
