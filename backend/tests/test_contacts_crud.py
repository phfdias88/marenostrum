"""
Testes de CRUD basico de contatos (no contexto de UM tenant).
O isolamento entre tenants e' testado em test_multi_tenant.py.
"""


def _payload(**overrides):
    base = {
        "full_name": "Maria Silva",
        "phone": "(32) 99999-0001",
        "email": "maria@example.com",
        "address": "Rua A, 100",
        "neighborhood": "Centro",
        "city": "Juiz de Fora",
        "state": "MG",
        "type": "voter",
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------- Create


def test_create_contact_returns_201_and_id(auth_a):
    r = auth_a.post("/api/v1/contacts", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["full_name"] == "Maria Silva"
    assert body["id"]
    # lat/lng nao vieram no payload nem do geocoding (mockado pra None)
    assert body["latitude"] is None
    assert body["longitude"] is None


def test_create_contact_rejects_short_name(auth_a):
    r = auth_a.post("/api/v1/contacts", json=_payload(full_name="A"))
    assert r.status_code == 422  # Pydantic validation


def test_create_contact_rejects_invalid_email(auth_a):
    r = auth_a.post("/api/v1/contacts", json=_payload(email="not-an-email"))
    assert r.status_code == 422


def test_create_contact_duplicate_phone_returns_409(auth_a):
    auth_a.post("/api/v1/contacts", json=_payload(phone="(32) 99999-1111"))
    r = auth_a.post(
        "/api/v1/contacts",
        json=_payload(full_name="Outro", email="outro@example.com",
                      phone="(32) 99999-1111"),
    )
    assert r.status_code == 409
    assert "telefone" in r.json()["message"].lower()


# ------------------------------------------------------------------- List


def test_list_contacts_empty(auth_a):
    r = auth_a.get("/api/v1/contacts")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_contacts_pagination(auth_a):
    # Cria 7 contatos com telefones distintos
    for i in range(7):
        auth_a.post(
            "/api/v1/contacts",
            json=_payload(
                full_name=f"Contato {i}",
                phone=f"(32) 99999-{i:04d}",
                email=f"c{i}@example.com",
            ),
        )

    r = auth_a.get("/api/v1/contacts?limit=3&offset=0")
    body = r.json()
    assert body["total"] == 7
    assert len(body["items"]) == 3

    r2 = auth_a.get("/api/v1/contacts?limit=3&offset=3")
    assert len(r2.json()["items"]) == 3

    r3 = auth_a.get("/api/v1/contacts?limit=3&offset=6")
    assert len(r3.json()["items"]) == 1


def test_search_filters_by_name_ilike(auth_a):
    """
    NOTA: ILIKE case-insensitive em ASCII funciona em SQLite e Postgres.
    Case-insensitive com acentos (ex.: 'JOÃO' casar com 'João') requer
    collation Unicode — funciona em PG com lc_collate=pt_BR.UTF-8 mas NAO
    no SQLite default. Para acent-insensitivity real, no futuro: extensao
    unaccent do PG ou pre-normalizar full_name num campo separado.
    """
    auth_a.post("/api/v1/contacts", json=_payload(
        full_name="Joao da Silva", phone="(32) 1111-1111", email=None,
    ))
    auth_a.post("/api/v1/contacts", json=_payload(
        full_name="Maria Souza", phone="(32) 2222-2222", email=None,
    ))
    auth_a.post("/api/v1/contacts", json=_payload(
        full_name="Pedro Oliveira", phone="(32) 3333-3333", email=None,
    ))

    # Case-insensitive ASCII (cobre SQLite + Postgres)
    r = auth_a.get("/api/v1/contacts?search=JOAO")
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["full_name"] == "Joao da Silva"

    # Substring match no meio do nome
    r = auth_a.get("/api/v1/contacts?search=Souza")
    names = {it["full_name"] for it in r.json()["items"]}
    assert "Maria Souza" in names


# ---------------------------------------------------------------- Update


def test_update_contact_partial(auth_a):
    created = auth_a.post("/api/v1/contacts", json=_payload()).json()
    cid = created["id"]

    r = auth_a.put(
        f"/api/v1/contacts/{cid}",
        json={"city": "Belo Horizonte"},  # so 1 campo
    )
    assert r.status_code == 200
    body = r.json()
    assert body["city"] == "Belo Horizonte"
    # Outros campos preservados
    assert body["full_name"] == "Maria Silva"
    assert body["phone"] == "(32) 99999-0001"


def test_update_nonexistent_returns_404(auth_a):
    from uuid import uuid4
    r = auth_a.put(
        f"/api/v1/contacts/{uuid4()}",
        json={"city": "X"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- Delete


def test_delete_contact_returns_204_and_removes(auth_a):
    created = auth_a.post("/api/v1/contacts", json=_payload()).json()
    cid = created["id"]

    r = auth_a.delete(f"/api/v1/contacts/{cid}")
    assert r.status_code == 204

    r2 = auth_a.get(f"/api/v1/contacts/{cid}")
    assert r2.status_code == 404


def test_delete_nonexistent_returns_404(auth_a):
    from uuid import uuid4
    r = auth_a.delete(f"/api/v1/contacts/{uuid4()}")
    assert r.status_code == 404
