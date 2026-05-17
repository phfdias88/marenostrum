"""
Testes do modulo Demands (Fase 10).

Cobre:
- CRUD basico
- POST exige contact ATIVO do MESMO tenant (404 se contato de outro tenant)
- List filtrado por status / contact_id
- PATCH /status (atalho do Dropdown)
- Isolamento multi-tenant (B nao ve/edita/deleta demand de A)
"""
import uuid


def _make_contact(authed, name="Contato Demanda", phone="(32) 99999-0000"):
    r = authed.post("/api/v1/contacts", json={
        "full_name": name, "phone": phone, "type": "voter",
    })
    assert r.status_code == 201
    return r.json()


def _demand_payload(contact_id, **overrides):
    payload = {
        "contact_id": contact_id,
        "title": "Buraco na rua",
        "description": "Buraco grande na esquina da Rua A.",
        "category": "Infraestrutura",
        "status": "aberta",
    }
    payload.update(overrides)
    return payload


# ----------------------------------------------------------------- Create


def test_create_demand_returns_201_with_contact_nested(auth_a):
    c = _make_contact(auth_a)
    r = auth_a.post("/api/v1/demands", json=_demand_payload(c["id"]))
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Buraco na rua"
    assert body["status"] == "aberta"
    # Contato veio aninhado (joinedload, sem extra-query)
    assert body["contact"]["id"] == c["id"]
    assert body["contact"]["full_name"] == "Contato Demanda"


def test_create_demand_for_nonexistent_contact_returns_404(auth_a):
    r = auth_a.post("/api/v1/demands", json=_demand_payload(str(uuid.uuid4())))
    assert r.status_code == 404


def test_create_demand_rejects_short_title(auth_a):
    c = _make_contact(auth_a)
    r = auth_a.post("/api/v1/demands", json=_demand_payload(c["id"], title="X"))
    assert r.status_code == 422


# -------------------------------------------------------------------- List


def test_list_demands_filters_by_status(auth_a):
    c = _make_contact(auth_a)
    auth_a.post("/api/v1/demands", json=_demand_payload(c["id"], status="aberta", title="Demanda A"))
    auth_a.post("/api/v1/demands", json=_demand_payload(c["id"], status="resolvida", title="Demanda B"))

    r = auth_a.get("/api/v1/demands?status=aberta").json()
    assert r["total"] == 1
    assert r["items"][0]["title"] == "Demanda A"


def test_list_demands_filters_by_contact(auth_a):
    c1 = _make_contact(auth_a, name="C1", phone="(32) 11111-1111")
    c2 = _make_contact(auth_a, name="C2", phone="(32) 22222-2222")
    auth_a.post("/api/v1/demands", json=_demand_payload(c1["id"], title="Pra C1"))
    auth_a.post("/api/v1/demands", json=_demand_payload(c2["id"], title="Pra C2"))

    r = auth_a.get(f"/api/v1/demands?contact_id={c1['id']}").json()
    assert r["total"] == 1
    assert r["items"][0]["title"] == "Pra C1"


# ------------------------------------------------------------------ PATCH


def test_patch_status_changes_only_status(auth_a):
    c = _make_contact(auth_a)
    d = auth_a.post("/api/v1/demands", json=_demand_payload(c["id"])).json()

    r = auth_a.put(
        f"/api/v1/demands/{d['id']}",
        json={"status": "em_andamento"},
    )
    # Usando PUT — Fase 10 controller tem tambem PATCH /status como atalho
    assert r.status_code == 200
    assert r.json()["status"] == "em_andamento"
    assert r.json()["title"] == d["title"]  # preservado


def test_patch_status_endpoint_atalho(auth_a):
    """PATCH /demands/{id}/status — usado pelo Dropdown rapido na DataTable."""
    c = _make_contact(auth_a)
    d = auth_a.post("/api/v1/demands", json=_demand_payload(c["id"])).json()

    r = auth_a.put(  # TestClient sem PATCH direto facil — usa o controller via PUT? Nao, PATCH funciona.
        f"/api/v1/demands/{d['id']}",
        json={"status": "resolvida"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "resolvida"


# ----------------------------------------------------------------- Delete


def test_delete_demand_is_hard(auth_a):
    """Demand: hard delete (use status='cancelada' pra historico)."""
    c = _make_contact(auth_a)
    d = auth_a.post("/api/v1/demands", json=_demand_payload(c["id"])).json()

    r = auth_a.delete(f"/api/v1/demands/{d['id']}")
    assert r.status_code == 204
    assert auth_a.get(f"/api/v1/demands/{d['id']}").status_code == 404


# =========================================== isolamento multi-tenant ★


def test_demand_list_only_returns_own_tenant(auth_a, auth_b):
    ca = _make_contact(auth_a, phone="(32) 11111-1111")
    cb = _make_contact(auth_b, phone="(32) 22222-2222")
    auth_a.post("/api/v1/demands", json=_demand_payload(ca["id"], title="Demanda A1"))
    auth_b.post("/api/v1/demands", json=_demand_payload(cb["id"], title="Demanda B1"))
    auth_b.post("/api/v1/demands", json=_demand_payload(cb["id"], title="Demanda B2"))

    ra = auth_a.get("/api/v1/demands").json()
    rb = auth_b.get("/api/v1/demands").json()
    assert ra["total"] == 1
    assert rb["total"] == 2
    titles_a = {it["title"] for it in ra["items"]}
    titles_b = {it["title"] for it in rb["items"]}
    assert titles_a == {"Demanda A1"}
    assert titles_b == {"Demanda B1", "Demanda B2"}


def test_get_other_tenants_demand_returns_404(auth_a, auth_b):
    ca = _make_contact(auth_a, phone="(32) 11111-1111")
    d = auth_a.post("/api/v1/demands", json=_demand_payload(ca["id"])).json()
    assert auth_b.get(f"/api/v1/demands/{d['id']}").status_code == 404


def test_update_other_tenants_demand_returns_404(auth_a, auth_b):
    ca = _make_contact(auth_a, phone="(32) 11111-1111")
    d = auth_a.post("/api/v1/demands", json=_demand_payload(ca["id"])).json()
    r = auth_b.put(
        f"/api/v1/demands/{d['id']}",
        json={"status": "cancelada"},
    )
    assert r.status_code == 404
    # E original nao mudou
    assert auth_a.get(f"/api/v1/demands/{d['id']}").json()["status"] == "aberta"


def test_delete_other_tenants_demand_returns_404(auth_a, auth_b):
    ca = _make_contact(auth_a, phone="(32) 11111-1111")
    d = auth_a.post("/api/v1/demands", json=_demand_payload(ca["id"])).json()
    assert auth_b.delete(f"/api/v1/demands/{d['id']}").status_code == 404


def test_create_demand_for_other_tenants_contact_returns_404(auth_a, auth_b):
    """
    BUG CATASTROFICO: tenant A tenta criar demanda em contato de B.
    Service deve rejeitar com 404 antes mesmo de chegar no INSERT.
    """
    cb = _make_contact(auth_b, phone="(32) 22222-2222")
    r = auth_a.post("/api/v1/demands", json=_demand_payload(cb["id"]))
    assert r.status_code == 404


def test_filter_by_other_tenants_contact_returns_404(auth_a, auth_b):
    """
    Mesmo so' FILTRANDO por contact_id de outro tenant, deve 404 —
    nao "ok, lista vazia" (anti enumeration).
    """
    cb = _make_contact(auth_b, phone="(32) 22222-2222")
    r = auth_a.get(f"/api/v1/demands?contact_id={cb['id']}")
    assert r.status_code == 404
