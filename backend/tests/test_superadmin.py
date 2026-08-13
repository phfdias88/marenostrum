"""
Painel do Superadministrador (Mare Nostrum) — gerência cross-tenant.

Cobre:
1. Gate: quem NÃO é superadmin toma 403 em qualquer rota /admin/*.
2. Superadmin lista TODOS os tenants (cross-tenant).
3. Cria conta de CORTESIA: titular com is_account_owner=True, tenant ativo
   (sem billing) e login funcionando com a senha provisória.
4. Reseta a senha do titular de outro cliente.
5. Ações administrativas só atingem TITULARES (não membros comuns).
"""
from app.core.security import create_access_token
from app.models.tenant import Tenant
from app.models.user import User, UserRole


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_superadmin(db_session, tenant_a):
    """Promove o owner do tenant_a a superadmin e devolve um token dele."""
    tenant, user, _ = tenant_a
    user.is_superadmin = True
    db_session.commit()
    return create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role.value,
    )


def test_admin_routes_require_superadmin(client, tenant_a):
    _, _, token = tenant_a  # owner comum, NÃO superadmin
    r = client.get("/api/v1/admin/tenants", headers=_auth(token))
    assert r.status_code == 403
    r = client.post(
        "/api/v1/admin/tenants",
        headers=_auth(token),
        json={"name": "X", "email": "x@x.com"},
    )
    assert r.status_code == 403


def test_superadmin_lists_all_tenants(client, tenant_a, tenant_b, db_session):
    token = _make_superadmin(db_session, tenant_a)
    r = client.get("/api/v1/admin/tenants", headers=_auth(token))
    assert r.status_code == 200
    slugs = {t["slug"] for t in r.json()["items"]}
    # Cross-tenant: enxerga os DOIS (A e B) — ao contrário do painel de equipe.
    assert "alpha" in slugs and "bravo" in slugs


def test_create_comp_account_and_login(client, tenant_a, db_session):
    token = _make_superadmin(db_session, tenant_a)
    r = client.post(
        "/api/v1/admin/tenants",
        headers=_auth(token),
        json={"name": "Dr. Teste Cortesia", "email": "cortesia@example.com"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "cortesia@example.com"
    temp = body["temp_password"]
    assert len(temp) >= 10

    # O titular nasceu com is_account_owner=True e tenant ativo (sem billing).
    owner = db_session.query(User).filter(User.email == "cortesia@example.com").one()
    assert owner.is_account_owner is True
    assert owner.role == UserRole.OWNER
    tenant = db_session.get(Tenant, owner.tenant_id)
    assert tenant.subscription_status == "active"

    # E consegue logar com a senha provisória (conta 100% funcional, grátis).
    login = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": "cortesia@example.com", "password": temp},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_courtesy_account_with_usage_limit(client, tenant_a, db_session):
    """Cortesia COM prazo: o limite é gravado no titular e o relógio só começa
    no 1º login (first_login_at/expires_at nascem vazios)."""
    token = _make_superadmin(db_session, tenant_a)
    r = client.post(
        "/api/v1/admin/tenants",
        headers=_auth(token),
        json={
            "name": "Político Teste",
            "email": "cortesia48@example.com",
            "usage_limit_hours": 48,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["usage_limit_hours"] == 48

    owner = db_session.query(User).filter(User.email == "cortesia48@example.com").one()
    assert owner.usage_limit_hours == 48
    assert owner.first_login_at is None  # relógio parado até o 1º login
    assert owner.expires_at is None

    # Ao logar, o AuthService materializa a expiração (regra já existente).
    login = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": r.json()["tenant_slug"],
            "email": "cortesia48@example.com",
            "password": r.json()["temp_password"],
        },
    )
    assert login.status_code == 200
    db_session.refresh(owner)
    assert owner.first_login_at is not None
    assert owner.expires_at is not None
    # JWT capado à janela de 48h (não o TTL padrão de 7 dias).
    assert login.json()["expires_in"] <= 48 * 3600 + 5

    # A listagem do painel expõe o prazo pro superadmin acompanhar.
    listed = client.get("/api/v1/admin/tenants", headers=_auth(token)).json()
    row = next(t for t in listed["items"] if t["titular_email"] == "cortesia48@example.com")
    assert row["titular_usage_limit_hours"] == 48
    assert row["titular_expires_at"] is not None


def test_courtesy_account_without_limit_is_unlimited(client, tenant_a, db_session):
    token = _make_superadmin(db_session, tenant_a)
    r = client.post(
        "/api/v1/admin/tenants",
        headers=_auth(token),
        json={"name": "Sem Prazo", "email": "semprazo@example.com", "usage_limit_hours": 0},
    )
    assert r.status_code == 201
    assert r.json()["usage_limit_hours"] is None  # 0 normalizado pra NULL
    owner = db_session.query(User).filter(User.email == "semprazo@example.com").one()
    assert owner.usage_limit_hours is None


def test_superadmin_resets_titular_of_another_tenant(client, tenant_a, tenant_b, db_session):
    token = _make_superadmin(db_session, tenant_a)
    # Marca o owner do tenant_b como titular (no fluxo real, provisioning/seed faz).
    _, owner_b, _ = tenant_b
    owner_b.is_account_owner = True
    db_session.commit()

    r = client.post(
        f"/api/v1/admin/users/{owner_b.id}/reset-password",
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert len(r.json()["temp_password"]) >= 10


def test_tenant_admin_cannot_set_usage_limit_on_invite(client, tenant_a, db_session):
    """RBAC: só a Mare Nostrum define PRAZO de acesso. O dono do tenant (que
    paga) convida a equipe dele, mas não emite acesso temporário."""
    _, _, owner_token = tenant_a  # owner comum, NÃO superadmin
    r = client.post(
        "/api/v1/auth/users",
        headers=_auth(owner_token),
        json={
            "email": "tentativa@example.com",
            "full_name": "Tentativa Trial",
            "role": "staff",
            "usage_limit_hours": 2,
        },
    )
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"
    # E o usuário NÃO foi criado.
    assert (
        db_session.query(User).filter(User.email == "tentativa@example.com").first()
        is None
    )


def test_tenant_admin_can_invite_without_limit(client, tenant_a, db_session):
    """O fluxo normal do cliente segue livre (sem prazo = sem restrição)."""
    _, _, owner_token = tenant_a
    r = client.post(
        "/api/v1/auth/users",
        headers=_auth(owner_token),
        json={
            "email": "equipe@example.com",
            "full_name": "Membro Equipe",
            "role": "staff",
            "usage_limit_hours": 0,  # 0 = sem prazo → permitido
        },
    )
    assert r.status_code in (200, 201)
    u = db_session.query(User).filter(User.email == "equipe@example.com").one()
    assert u.usage_limit_hours is None


def test_superadmin_can_set_usage_limit_on_invite(client, tenant_a, db_session):
    token = _make_superadmin(db_session, tenant_a)
    r = client.post(
        "/api/v1/auth/users",
        headers=_auth(token),
        json={
            "email": "trialok@example.com",
            "full_name": "Trial Permitido",
            "role": "staff",
            "usage_limit_hours": 3,
        },
    )
    assert r.status_code in (200, 201), r.text
    u = db_session.query(User).filter(User.email == "trialok@example.com").one()
    assert u.usage_limit_hours == 3


def test_tenant_admin_cannot_invite_owner_role(client, tenant_a):
    """Escalonamento de privilégio: 'owner' não é papel convidável (Pydantic
    só aceita manager/staff/volunteer)."""
    _, _, owner_token = tenant_a
    r = client.post(
        "/api/v1/auth/users",
        headers=_auth(owner_token),
        json={"email": "novodono@example.com", "full_name": "Novo Dono", "role": "owner"},
    )
    assert r.status_code == 422


def test_admin_actions_only_target_titulares(client, tenant_a, tenant_b, db_session):
    token = _make_superadmin(db_session, tenant_a)
    # owner_b NÃO é titular (is_account_owner=False por padrão) → ação barrada.
    _, owner_b, _ = tenant_b
    assert owner_b.is_account_owner is False
    r = client.post(
        f"/api/v1/admin/users/{owner_b.id}/reset-password",
        headers=_auth(token),
    )
    assert r.status_code == 403


# =============================================== ENTRAR COMO (impersonação)


def test_impersonation_requires_superadmin(client, tenant_a, tenant_b):
    """Cliente comum não abre o ambiente de ninguém."""
    tenant_b_obj = tenant_b[0]
    _, _, owner_token = tenant_a
    r = client.post(
        f"/api/v1/admin/tenants/{tenant_b_obj.id}/impersonate",
        headers=_auth(owner_token),
    )
    assert r.status_code == 403


def test_superadmin_impersonates_and_sees_client_data(
    client, tenant_a, tenant_b, db_session
):
    """O superadmin entra no ambiente do cliente e enxerga os dados DE LÁ."""
    token = _make_superadmin(db_session, tenant_a)
    tenant_b_obj, owner_b, _ = tenant_b

    r = client.post(
        f"/api/v1/admin/tenants/{tenant_b_obj.id}/impersonate",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_name"] == tenant_b_obj.name
    # Sessão CURTA (1h), não os 7 dias de um login normal.
    assert body["expires_in"] <= 3600

    imp = body["access_token"]
    # Com o token de visita, /me reporta o tenant do CLIENTE...
    me = client.get("/api/v1/auth/me", headers=_auth(imp)).json()
    assert me["tenant_id"] == str(tenant_b_obj.id)
    # ...e a identidade REAL de quem entrou (auditoria aponta pro superadmin).
    assert me["user_id"] == str(tenant_a[1].id)
    assert me["impersonating"] is True

    # E a equipe listada é a do cliente visitado, não a do superadmin.
    users = client.get("/api/v1/auth/users", headers=_auth(imp)).json()
    emails = {u["email"] for u in users}
    assert owner_b.email in emails
    assert tenant_a[1].email not in emails


def test_impersonation_token_dies_when_superadmin_flag_is_revoked(
    client, tenant_a, tenant_b, db_session
):
    """Revogar o super-acesso invalida a sessão de visita NA HORA (a flag é
    re-checada no banco a cada request, não confiada ao token)."""
    token = _make_superadmin(db_session, tenant_a)
    tenant_b_obj = tenant_b[0]
    imp = client.post(
        f"/api/v1/admin/tenants/{tenant_b_obj.id}/impersonate",
        headers=_auth(token),
    ).json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=_auth(imp)).status_code == 200

    tenant_a[1].is_superadmin = False
    db_session.commit()
    assert client.get("/api/v1/auth/me", headers=_auth(imp)).status_code == 401


def test_cannot_chain_impersonation(client, tenant_a, tenant_b, db_session):
    """De dentro de uma visita não se pula pra outra (rastro ficaria confuso)."""
    token = _make_superadmin(db_session, tenant_a)
    tenant_b_obj = tenant_b[0]
    imp = client.post(
        f"/api/v1/admin/tenants/{tenant_b_obj.id}/impersonate",
        headers=_auth(token),
    ).json()["access_token"]
    r = client.post(
        f"/api/v1/admin/tenants/{tenant_a[0].id}/impersonate", headers=_auth(imp)
    )
    assert r.status_code == 403
