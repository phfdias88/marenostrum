"""
TESTES DE ISOLAMENTO MULTI-TENANT — O CORACAO DA SEGURANCA DESTE SaaS.

Princípio: vazamento de dados de eleitores entre campanhas e' FALHA CRITICA.
Cada teste aqui simula um cenario onde um bug poderia causar vazamento, e
prova que NAO HA vazamento. Se algum destes testes falhar, NAO DEPLOY.

Padrao dos testes: tenant A cria recursos, tenant B tenta acessar/alterar/
deletar, e verificamos que B "nao ve" os recursos do A (404, NUNCA 200/403).

Por que 404 e nao 403: ate' a EXISTENCIA do recurso de outro tenant deve
ser invisivel. 403 diria "esse recurso existe mas voce nao pode" — leak de
informacao. 404 = "nao existe pra voce", consistente com nao existir.
"""


def _make_contact(authed, **overrides):
    payload = {
        "full_name": "Contato Teste",
        "phone": "(32) 99999-0000",
        "email": "teste@example.com",
        "type": "voter",
    }
    payload.update(overrides)
    r = authed.post("/api/v1/contacts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# =================================================================== LIST


def test_list_only_returns_own_tenant_contacts(auth_a, auth_b):
    """A cria 2, B cria 3. GET /contacts de A so ve 2; de B so ve 3."""
    _make_contact(auth_a, phone="(32) 1111-1111", email="a1@example.com")
    _make_contact(auth_a, phone="(32) 1111-1112", email="a2@example.com")
    _make_contact(auth_b, phone="(32) 2222-2221", email="b1@example.com")
    _make_contact(auth_b, phone="(32) 2222-2222", email="b2@example.com")
    _make_contact(auth_b, phone="(32) 2222-2223", email="b3@example.com")

    ra = auth_a.get("/api/v1/contacts").json()
    rb = auth_b.get("/api/v1/contacts").json()

    assert ra["total"] == 2
    assert rb["total"] == 3
    # Garante que nenhum ID de B aparece em A e vice-versa
    a_ids = {c["id"] for c in ra["items"]}
    b_ids = {c["id"] for c in rb["items"]}
    assert a_ids.isdisjoint(b_ids)


def test_list_for_map_only_returns_own_tenant(auth_a, auth_b):
    """GET /contacts/map tambem filtra por tenant_id."""
    # A cria contato COM coords explicitas (geocoding e' mockado pra None)
    _make_contact(auth_a, phone="(32) 1111-1111",
                  latitude=-21.76, longitude=-43.35)
    _make_contact(auth_b, phone="(32) 2222-2222",
                  latitude=-22.90, longitude=-43.20)

    ra = auth_a.get("/api/v1/contacts/map").json()
    rb = auth_b.get("/api/v1/contacts/map").json()

    assert len(ra) == 1
    assert len(rb) == 1
    assert ra[0]["id"] != rb[0]["id"]


def test_search_only_searches_own_tenant(auth_a, auth_b):
    """A tem 'João Silva'; B tem 'João Souza'. Cada um so ve o proprio."""
    _make_contact(auth_a, full_name="João Silva",
                  phone="(32) 1111-1111", email="a@example.com")
    _make_contact(auth_b, full_name="João Souza",
                  phone="(32) 2222-2222", email="b@example.com")

    ra = auth_a.get("/api/v1/contacts?search=João").json()
    rb = auth_b.get("/api/v1/contacts?search=João").json()

    assert ra["total"] == 1 and ra["items"][0]["full_name"] == "João Silva"
    assert rb["total"] == 1 and rb["items"][0]["full_name"] == "João Souza"


# ================================================================ DETAIL


def test_get_other_tenants_contact_returns_404(auth_a, auth_b):
    contact_a = _make_contact(auth_a, phone="(32) 1111-1111", email="a@example.com")

    # B tenta GET com o ID de A
    r = auth_b.get(f"/api/v1/contacts/{contact_a['id']}")
    assert r.status_code == 404


# ================================================================ UPDATE


def test_update_other_tenants_contact_returns_404(auth_a, auth_b):
    contact_a = _make_contact(auth_a, phone="(32) 1111-1111", email="a@example.com")

    r = auth_b.put(
        f"/api/v1/contacts/{contact_a['id']}",
        json={"full_name": "HACKED"},
    )
    assert r.status_code == 404

    # E o original do A nao foi alterado
    ra = auth_a.get(f"/api/v1/contacts/{contact_a['id']}").json()
    assert ra["full_name"] == "Contato Teste"


def test_update_cannot_change_own_tenant_id_via_payload(auth_a, auth_b):
    """
    Defense-in-depth: mesmo que cliente envie tenant_id no body, repo
    deve ignorar — o tenant_id sempre vem do JWT.
    (Schema Pydantic ja' nao aceita tenant_id, mas testamos o caminho.)
    """
    contact_a = _make_contact(auth_a, phone="(32) 1111-1111", email="a@example.com")
    tenant_b_id = "00000000-0000-0000-0000-000000000099"

    # Pydantic ignora campos extras com extra="ignore" (default). O update
    # nao deveria mover o contato pra outro tenant.
    auth_a.put(
        f"/api/v1/contacts/{contact_a['id']}",
        json={"full_name": "novo", "tenant_id": tenant_b_id},
    )

    # A ainda ve; B nao ve.
    assert auth_a.get(f"/api/v1/contacts/{contact_a['id']}").status_code == 200
    assert auth_b.get(f"/api/v1/contacts/{contact_a['id']}").status_code == 404


# ================================================================ DELETE


def test_delete_other_tenants_contact_returns_404(auth_a, auth_b):
    contact_a = _make_contact(auth_a, phone="(32) 1111-1111", email="a@example.com")

    r = auth_b.delete(f"/api/v1/contacts/{contact_a['id']}")
    assert r.status_code == 404

    # E o contato de A continua la
    assert auth_a.get(f"/api/v1/contacts/{contact_a['id']}").status_code == 200


# ================================================================ CREATE


def test_unique_phone_is_per_tenant_not_global(auth_a, auth_b):
    """
    Telefone unico DENTRO de um tenant — nao globalmente.
    Mesmo numero pode existir em campanhas distintas (eleitor pode
    apoiar candidatos diferentes; cada base e' independente).
    """
    _make_contact(auth_a, phone="(32) 99999-1234", email="a@example.com")
    # B tenta o mesmo numero — deve funcionar
    r = auth_b.post(
        "/api/v1/contacts",
        json={
            "full_name": "Outro",
            "phone": "(32) 99999-1234",
            "email": "b@example.com",
            "type": "voter",
        },
    )
    assert r.status_code == 201


# ================================================================ IMPORT


def test_import_csv_only_inserts_into_own_tenant(auth_a, auth_b):
    """
    CSV importado pelo A vai TODO pro tenant A — mesmo se o telefone
    ja existe no B (nao ha colisao cross-tenant).
    """
    # B ja tem o telefone X
    _make_contact(auth_b, phone="(32) 99999-7777", email="b@example.com")

    # A importa CSV com esse mesmo telefone
    csv = (
        "Nome;Telefone;Email\n"
        "Joao A;(32) 99999-7777;a-import@example.com\n"
    ).encode("utf-8-sig")

    r = auth_a.post(
        "/api/v1/contacts/import",
        files={"file": ("teste.csv", csv, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    # Deve ter importado (telefone do outro tenant nao bloqueia)
    assert body["imported"] == 1
    assert body["skipped"] == 0

    # B nao ve o novo contato; A ve
    assert auth_a.get("/api/v1/contacts").json()["total"] == 1
    assert auth_b.get("/api/v1/contacts").json()["total"] == 1  # ainda so o dele


def test_import_csv_rejects_phone_existing_in_same_tenant(auth_a):
    """Mas dentro do MESMO tenant, telefone duplicado e' pulado."""
    _make_contact(auth_a, phone="(32) 99999-8888", email="ja@example.com")

    csv = (
        "Nome;Telefone;Email\n"
        "Repetido;(32) 99999-8888;novo@example.com\n"
    ).encode("utf-8-sig")

    r = auth_a.post(
        "/api/v1/contacts/import",
        files={"file": ("teste.csv", csv, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 0
    assert body["skipped"] == 1
    assert any("ja cadastrado" in e["message"].lower() for e in body["errors"])
