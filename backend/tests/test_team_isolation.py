"""
Isolamento multi-tenant do painel de EQUIPE + titular da assinatura.

Regressão da auditoria do PO (jul/2026):
1. GET /auth/users NUNCA pode listar usuário de outro tenant (Tenant Data Leak).
2. Convidado nasce is_account_owner=False; o titular (provisionamento do
   billing) nasce True.
3. O papel do TITULAR não pode ser alterado — sem isso, um convidado promovido
   a Dono rebaixava o titular e o desativava (cadeia de tomada da conta).
"""
from app.core.security import create_access_token, hash_password
from app.models.subscription import Subscription
from app.models.user import User, UserRole
from app.services.provisioning import provision_from_subscription


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_list_users_never_leaks_other_tenant(client, tenant_a, tenant_b):
    _, user_a, token_a = tenant_a
    _, user_b, token_b = tenant_b

    r = client.get("/api/v1/auth/users", headers=_auth(token_a))
    assert r.status_code == 200
    emails_a = {u["email"] for u in r.json()}
    assert user_a.email in emails_a
    # A NUNCA vê usuário do tenant B (e vice-versa).
    assert user_b.email not in emails_a

    r = client.get("/api/v1/auth/users", headers=_auth(token_b))
    emails_b = {u["email"] for u in r.json()}
    assert user_b.email in emails_b
    assert user_a.email not in emails_b


def test_invited_user_is_not_account_owner(client, tenant_a, db_session):
    _, _, token_a = tenant_a
    r = client.post(
        "/api/v1/auth/users",
        headers=_auth(token_a),
        json={"email": "convidado@example.com", "full_name": "Convidado Um", "role": "manager"},
    )
    assert r.status_code in (200, 201)
    invited = (
        db_session.query(User).filter(User.email == "convidado@example.com").one()
    )
    assert invited.is_account_owner is False

    # E a listagem expõe a flag (pro badge da UI).
    r = client.get("/api/v1/auth/users", headers=_auth(token_a))
    by_email = {u["email"]: u for u in r.json()}
    assert by_email["convidado@example.com"]["is_account_owner"] is False


def test_provisioning_marks_titular(db_session):
    sub = Subscription(
        status="pending", plan="bi", cycle="MONTHLY",
        external_reference="iso-test", billing_email="titular@example.com",
        buyer_name="Titular Teste",
    )
    db_session.add(sub)
    db_session.flush()
    result = provision_from_subscription(db_session, sub)
    db_session.flush()
    assert result.owner.is_account_owner is True


def test_titular_role_cannot_be_changed(client, tenant_a, db_session):
    tenant, titular, _ = tenant_a
    # Marca o owner do fixture como TITULAR (no billing real, o webhook faz).
    titular.is_account_owner = True
    # Convidado promovido a Dono (o cenário de risco).
    guest = User(
        tenant_id=tenant.id,
        email="dono-convidado@example.com",
        full_name="Dono Convidado",
        hashed_password=hash_password("Senha@Forte123"),
        role=UserRole.OWNER,
        is_active=True,
        is_account_owner=False,
    )
    db_session.add(guest)
    db_session.commit()
    guest_token = create_access_token(
        user_id=guest.id, tenant_id=tenant.id, role="owner",
    )

    r = client.post(
        f"/api/v1/auth/users/{titular.id}/role",
        headers=_auth(guest_token),
        json={"role": "staff"},
    )
    assert r.status_code == 403
    db_session.refresh(titular)
    assert titular.role == UserRole.OWNER  # intacto
