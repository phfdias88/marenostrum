"""
Testes do soft delete em Contact (Fase 10).

Validam que:
- DELETE da API marca is_active=False (preserva row no DB)
- Contato soft-deleted SOME das listas/buscas/mapa
- GET por ID retorna 404 (consistente com hard delete da perspectiva do client)
- Interactions e Demands do contato soft-deleted CONTINUAM no DB
"""
from app.models.contact import Contact


def test_soft_delete_keeps_row_but_marks_inactive(auth_a, db_session):
    """DELETE da API: row continua no DB com is_active=False."""
    created = auth_a.post("/api/v1/contacts", json={
        "full_name": "Para Apagar",
        "phone": "(32) 99999-1111",
        "type": "voter",
    }).json()
    cid = created["id"]

    r = auth_a.delete(f"/api/v1/contacts/{cid}")
    assert r.status_code == 204

    # API: 404 como se nao existisse
    assert auth_a.get(f"/api/v1/contacts/{cid}").status_code == 404

    # DB: row continua la, is_active=False
    import uuid
    row = db_session.get(Contact, uuid.UUID(cid))
    assert row is not None
    assert row.is_active is False
    assert row.full_name == "Para Apagar"  # nome preservado


def test_soft_deleted_does_not_appear_in_list(auth_a):
    auth_a.post("/api/v1/contacts", json={
        "full_name": "Ativo", "phone": "(32) 1111-1111", "type": "voter",
    })
    apagar = auth_a.post("/api/v1/contacts", json={
        "full_name": "Apagado", "phone": "(32) 2222-2222", "type": "voter",
    }).json()
    auth_a.delete(f"/api/v1/contacts/{apagar['id']}")

    r = auth_a.get("/api/v1/contacts").json()
    assert r["total"] == 1
    assert r["items"][0]["full_name"] == "Ativo"


def test_soft_deleted_does_not_appear_in_search(auth_a):
    apagar = auth_a.post("/api/v1/contacts", json={
        "full_name": "Joao Apagado", "phone": "(32) 2222-2222", "type": "voter",
    }).json()
    auth_a.delete(f"/api/v1/contacts/{apagar['id']}")

    r = auth_a.get("/api/v1/contacts?search=Joao").json()
    assert r["total"] == 0


def test_soft_deleted_does_not_appear_in_map(auth_a):
    """Contato soft-deletado NAO deve aparecer no mapa."""
    apagar = auth_a.post("/api/v1/contacts", json={
        "full_name": "Geo", "phone": "(32) 2222-2222", "type": "voter",
        "latitude": -21.76, "longitude": -43.35,
    }).json()
    # Antes do delete: aparece
    assert len(auth_a.get("/api/v1/contacts/map").json()) == 1
    auth_a.delete(f"/api/v1/contacts/{apagar['id']}")
    # Depois: nao aparece
    assert len(auth_a.get("/api/v1/contacts/map").json()) == 0


def test_soft_deleted_cannot_be_updated(auth_a):
    """PUT em contato soft-deletado retorna 404 (filter is_active no UPDATE)."""
    created = auth_a.post("/api/v1/contacts", json={
        "full_name": "Original", "phone": "(32) 1111-1111", "type": "voter",
    }).json()
    auth_a.delete(f"/api/v1/contacts/{created['id']}")

    r = auth_a.put(
        f"/api/v1/contacts/{created['id']}",
        json={"full_name": "Tentativa de ressurreicao"},
    )
    assert r.status_code == 404


def test_webhook_does_not_link_to_soft_deleted_contact(
    client, auth_a, tenant_a_with_secret, db_session,
):
    """Webhook nao 'ressuscita' contato apagado — vira orfa."""
    tenant, _, _ = tenant_a_with_secret
    created = auth_a.post("/api/v1/contacts", json={
        "full_name": "Para Apagar",
        "phone": "(32) 99999-8888",
        "type": "voter",
    }).json()
    auth_a.delete(f"/api/v1/contacts/{created['id']}")

    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json={"phone": "(32) 99999-8888", "event": "mensagem_recebida"},
        headers={"X-Webhook-Secret": "secret-tenant-alpha-1234567890"},
    )
    assert r.status_code == 200
    assert r.json()["contact_matched"] is False
    assert r.json()["contact_id"] is None


def test_duplicate_phone_blocked_even_when_existing_is_soft_deleted(auth_a):
    """
    Phone de contato soft-deletado AINDA bloqueia novo cadastro com mesmo phone.
    (Decisao conservadora — unique constraint do DB inclui inactive.)
    """
    created = auth_a.post("/api/v1/contacts", json={
        "full_name": "Antigo", "phone": "(32) 99999-7777", "type": "voter",
    }).json()
    auth_a.delete(f"/api/v1/contacts/{created['id']}")

    r = auth_a.post("/api/v1/contacts", json={
        "full_name": "Novo", "phone": "(32) 99999-7777", "type": "voter",
    })
    assert r.status_code == 409
