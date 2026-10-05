"""
Exclusão de usuários da equipe.

Relato do sócio (jul/2026): "não consigo excluir os antigos". Causa: contas
com papel Administrador (Dono) exigiam ser REBAIXADAS antes de excluir — dois
passos nada óbvios. Agora o Dono exclui outro Dono direto; só o TITULAR da
assinatura permanece protegido (é a identidade dona do cliente).
"""
from app.core.security import hash_password
from app.models.user import User, UserRole


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _add(db, tenant, email, role=UserRole.OWNER, titular=False):
    u = User(
        tenant_id=tenant.id, email=email, full_name="Antigo",
        hashed_password=hash_password("Senha@Forte123"), role=role,
        is_active=True, is_account_owner=titular,
    )
    db.add(u)
    db.commit()
    return u


def test_owner_can_delete_another_owner_directly(client, tenant_a, db_session):
    """O caso do relato: excluir um Administrador (Dono) antigo, em 1 passo."""
    tenant, _, token = tenant_a
    antigo = _add(db_session, tenant, "dono-antigo@example.com")
    # Guarda o id ANTES: depois do DELETE o objeto está expirado e tocar em
    # qualquer atributo levanta ObjectDeletedError.
    uid = antigo.id
    r = client.delete(f"/api/v1/auth/users/{uid}", headers=_auth(token))
    assert r.status_code == 204, r.text
    # expire_all(): a exclusão rodou em OUTRA sessão; sem isso a consulta
    # devolveria o objeto do cache de identidade e o teste mentiria.
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == uid).first() is None


def test_titular_cannot_be_deleted(client, tenant_a, db_session):
    """O titular da assinatura segue protegido (deixaria a conta órfã)."""
    tenant, _, token = tenant_a
    titular = _add(db_session, tenant, "titular@example.com", titular=True)
    r = client.delete(f"/api/v1/auth/users/{titular.id}", headers=_auth(token))
    assert r.status_code == 403
    assert "titular" in r.json()["message"].lower()
    assert db_session.get(User, titular.id) is not None


def test_cannot_delete_self(client, tenant_a):
    _, me, token = tenant_a
    r = client.delete(f"/api/v1/auth/users/{me.id}", headers=_auth(token))
    assert r.status_code == 403


def test_manager_cannot_delete_owner(client, tenant_a, db_session):
    """Coordenador não derruba Administrador (anti-escalonamento)."""
    from app.core.security import create_access_token

    tenant, _, _ = tenant_a
    alvo = _add(db_session, tenant, "dono2@example.com")
    manager = _add(db_session, tenant, "coord@example.com", role=UserRole.MANAGER)
    mtoken = create_access_token(
        user_id=manager.id, tenant_id=tenant.id, role="manager",
    )
    r = client.delete(f"/api/v1/auth/users/{alvo.id}", headers=_auth(mtoken))
    assert r.status_code == 403
    assert db_session.get(User, alvo.id) is not None


def test_cannot_delete_user_from_another_tenant(client, tenant_a, tenant_b):
    """Isolamento: não dá pra excluir usuário de outro cliente."""
    _, _, token_a = tenant_a
    _, owner_b, _ = tenant_b
    r = client.delete(f"/api/v1/auth/users/{owner_b.id}", headers=_auth(token_a))
    assert r.status_code == 404
