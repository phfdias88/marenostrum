"""
Login sem `tenant_slug` — a campanha é resolvida pelo e-mail.

Incidente (jul/2026): o formulário mandava `tenant_slug` FIXO
("marenostrum-admin"), então TODO cliente de outra campanha recebia
"Credenciais inválidas" mesmo com a senha correta — os dois clientes reais
ficaram sem conseguir entrar. Aqui garantimos o comportamento correto.
"""
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User, UserRole

PWD = "Senha@Forte123"


def _add_user(db, tenant, email, pwd=PWD, role=UserRole.OWNER, active=True):
    u = User(
        tenant_id=tenant.id, email=email, full_name="Fulano",
        hashed_password=hash_password(pwd), role=role, is_active=active,
    )
    db.add(u)
    db.commit()
    return u


def test_login_without_slug_finds_the_right_campaign(client, tenant_b, db_session):
    """Cliente de OUTRA campanha entra sem informar slug (o caso do incidente)."""
    tenant, owner, _ = tenant_b
    r = client.post(
        "/api/v1/auth/login",
        json={"email": owner.email, "password": PWD},  # sem tenant_slug
    )
    assert r.status_code == 200, r.text
    assert r.json()["tenant_id"] == str(tenant.id)


def test_wrong_password_still_401(client, tenant_b):
    _, owner, _ = tenant_b
    r = client.post(
        "/api/v1/auth/login", json={"email": owner.email, "password": "errada-123"}
    )
    assert r.status_code == 401


def test_unknown_email_still_401(client, tenant_a):
    r = client.post(
        "/api/v1/auth/login", json={"email": "ninguem@example.com", "password": PWD}
    )
    assert r.status_code == 401


def test_inactive_user_cannot_login(client, tenant_a, db_session):
    """Usuário DESATIVADO não entra (foi o que travou os titulares)."""
    tenant, _, _ = tenant_a
    _add_user(db_session, tenant, "inativo@example.com", active=False)
    r = client.post(
        "/api/v1/auth/login", json={"email": "inativo@example.com", "password": PWD}
    )
    assert r.status_code == 401


def test_same_email_in_two_campaigns_asks_to_choose(client, tenant_a, tenant_b, db_session):
    """Mesmo e-mail+senha em 2 campanhas: o backend NÃO adivinha — pede escolha."""
    _add_user(db_session, tenant_a[0], "duplo@example.com")
    _add_user(db_session, tenant_b[0], "duplo@example.com", role=UserRole.MANAGER)

    r = client.post(
        "/api/v1/auth/login", json={"email": "duplo@example.com", "password": PWD}
    )
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "choose_tenant"
    slugs = {o["tenant_slug"] for o in body["options"]}
    assert slugs == {tenant_a[0].slug, tenant_b[0].slug}

    # Com a campanha escolhida, entra normalmente.
    r2 = client.post(
        "/api/v1/auth/login",
        json={
            "email": "duplo@example.com",
            "password": PWD,
            "tenant_slug": tenant_b[0].slug,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["tenant_id"] == str(tenant_b[0].id)


def test_explicit_slug_still_works(client, tenant_a):
    """Caminho antigo (com slug) continua válido — integrações não quebram."""
    tenant, owner, _ = tenant_a
    r = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": owner.email, "password": PWD},
    )
    assert r.status_code == 200


def test_login_in_inactive_tenant_is_blocked(client, db_session):
    """Campanha desativada não deixa ninguém entrar."""
    t = Tenant(name="Campanha Off", slug="campanha-off", is_active=False)
    db_session.add(t)
    db_session.flush()
    _add_user(db_session, t, "off@example.com")
    r = client.post(
        "/api/v1/auth/login", json={"email": "off@example.com", "password": PWD}
    )
    assert r.status_code == 401


# ============ senha provisória gerada pela plataforma (relato do PO) =========


def test_invited_member_logs_in_with_temp_password(client, tenant_a, db_session):
    """Membro criado pelo painel entra com a senha provisória, sem informar
    campanha. (Relato: "senha provisória dá credenciais inválidas".)"""
    tenant, owner, token = tenant_a
    r = client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "novo-membro@example.com", "full_name": "Novo Membro", "role": "staff"},
    )
    assert r.status_code in (200, 201), r.text
    temp = r.json()["temp_password"]

    # O banco guarda HASH (bcrypt), nunca a senha em texto puro.
    u = db_session.query(User).filter(User.email == "novo-membro@example.com").one()
    assert u.hashed_password != temp
    assert u.hashed_password.startswith("$2")  # bcrypt
    assert u.is_active is True

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "novo-membro@example.com", "password": temp},
    )
    assert login.status_code == 200, login.text


def test_courtesy_owner_logs_in_with_temp_password(client, tenant_a, db_session):
    """Titular de CORTESIA (tenant novo) entra com a senha provisória — este é
    o caso que o slug fixo do formulário quebrava."""
    from app.core.security import create_access_token

    tenant, user, _ = tenant_a
    user.is_superadmin = True
    db_session.commit()
    su = create_access_token(user_id=user.id, tenant_id=tenant.id, role="owner")

    r = client.post(
        "/api/v1/admin/tenants",
        headers={"Authorization": f"Bearer {su}"},
        json={"name": "Cliente Novo", "email": "titular-novo@example.com"},
    )
    assert r.status_code == 201, r.text
    temp = r.json()["temp_password"]

    # SEM tenant_slug — como o formulário público faz.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "titular-novo@example.com", "password": temp},
    )
    assert login.status_code == 200, login.text
