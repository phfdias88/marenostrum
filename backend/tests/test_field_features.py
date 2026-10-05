"""
Testes do pacote "features de campo do CRM" (jul/2026):

A) Normalizacao de telefone — normalize_phone/mask_phone + auto-vinculo do
   webhook quando o BotConversa manda o numero com DDI 55.
B) Inbox de leads orfaos do WhatsApp — listagem agrupada + relink.
C) Ranking de liderancas (leaderboard de cadastros).
D) Aging de demandas — filtro open_older_than_days.
E) Mutirao WhatsApp — filtros bairro/tipo na lista + interacao manual.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.utils.phone import mask_phone, normalize_phone

SECRET_A = "secret-tenant-alpha-1234567890"


def _contact_payload(name: str, phone: str, **extra) -> dict:
    return {"full_name": name, "phone": phone, "type": "voter", **extra}


def _webhook(client, tenant_id, phone: str, event: str = "mensagem_recebida"):
    return client.post(
        f"/api/v1/webhooks/botconversa/{tenant_id}",
        json={"event": event, "id": str(uuid.uuid4()), "phone": phone},
        headers={"X-Webhook-Secret": SECRET_A},
    )


# ================================================= A) normalizacao (unit)


def test_normalize_phone_rules():
    # Formatado BR -> so digitos
    assert normalize_phone("(21) 99999-1234") == "21999991234"
    # DDI 55 + celular (13 digitos) -> remove DDI
    assert normalize_phone("5521999991234") == "21999991234"
    # DDI 55 + fixo (12 digitos) -> remove DDI
    assert normalize_phone("552133334444") == "2133334444"
    # 11 digitos comecando com 55 = DDD 55 (Santa Maria/RS), NAO remove
    assert normalize_phone("55999991234") == "55999991234"
    # Menos de 8 digitos = nao e' telefone
    assert normalize_phone("999-1234") is None
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def test_mask_phone_last_4_digits():
    assert mask_phone("(21) 99999-1234") == "***1234"
    assert mask_phone("5521999991234") == "***1234"
    assert mask_phone(None) is None


# ================================== A) webhook casa telefone com DDI 55


def test_webhook_links_contact_when_phone_comes_with_ddi_55(
    client, auth_a, tenant_a_with_secret,
):
    """Cadastro '(21) 99999-1234' + webhook '5521999991234' = MESMO contato."""
    tenant, _, _ = tenant_a_with_secret
    created = auth_a.post(
        "/api/v1/contacts", json=_contact_payload("Zé do Zap", "(21) 99999-1234"),
    ).json()

    r = _webhook(client, tenant.id, "5521999991234")
    assert r.status_code == 200
    body = r.json()
    assert body["contact_matched"] is True
    assert body["contact_id"] == created["id"]


def test_webhook_normalized_match_still_tenant_isolated(
    client, auth_b, tenant_a_with_secret,
):
    """Contato em B com o numero normalizado NAO linka webhook de A."""
    tenant_a, _, _ = tenant_a_with_secret
    auth_b.post("/api/v1/contacts", json=_contact_payload("Do B", "(21) 96666-0000"))

    r = _webhook(client, tenant_a.id, "5521966660000")
    assert r.status_code == 200
    assert r.json()["contact_matched"] is False


# ============================================ B) inbox de orfas + relink


def test_orphan_inbox_groups_by_phone(
    client, auth_a, tenant_a_with_secret, db_session,
):
    tenant, _, _ = tenant_a_with_secret
    # 2 eventos do mesmo telefone + 1 de outro
    _webhook(client, tenant.id, "5521988887777")
    second = _webhook(client, tenant.id, "5521988887777", event="fluxo_concluido")
    _webhook(client, tenant.id, "5521977776666")

    # SQLite: CURRENT_TIMESTAMP tem precisao de segundo — os 2 eventos do
    # mesmo telefone empatam. Avanca o received_at do segundo pra tornar o
    # "last_event_type" deterministico (em PG real ha' microsegundos).
    from app.models.interaction import Interaction
    row = db_session.get(Interaction, uuid.UUID(second.json()["interaction_id"]))
    row.received_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    db_session.commit()

    r = auth_a.get("/api/v1/contacts/orphan-interactions")
    assert r.status_code == 200
    groups = r.json()
    assert len(groups) == 2
    by_phone = {g["phone"]: g for g in groups}
    g = by_phone["5521988887777"]
    assert g["count"] == 2
    assert g["phone_masked"] == "***7777"
    assert g["last_event_type"] == "fluxo_concluido"
    assert g["last_at"] is not None


def test_orphan_inbox_is_tenant_scoped(client, auth_b, tenant_a_with_secret):
    tenant_a, _, _ = tenant_a_with_secret
    _webhook(client, tenant_a.id, "5521955554444")
    assert auth_b.get("/api/v1/contacts/orphan-interactions").json() == []


def test_relink_matches_normalized_phone(client, auth_a, tenant_a_with_secret):
    """Orfa '5521988887777' + contato criado depois como '(21) 98888-7777'."""
    tenant, _, _ = tenant_a_with_secret
    _webhook(client, tenant.id, "5521988887777")
    _webhook(client, tenant.id, "5521988887777")

    # Sem contato correspondente: relinka 0 (idempotente/no-op)
    r = auth_a.post("/api/v1/contacts/orphan-interactions/relink")
    assert r.status_code == 200
    assert r.json()["relinked"] == 0

    created = auth_a.post(
        "/api/v1/contacts", json=_contact_payload("Lead Novo", "(21) 98888-7777"),
    ).json()

    r = auth_a.post("/api/v1/contacts/orphan-interactions/relink")
    assert r.json()["relinked"] == 2
    # Inbox esvaziou
    assert auth_a.get("/api/v1/contacts/orphan-interactions").json() == []
    # Interacoes agora aparecem na timeline do contato
    tl = auth_a.get(f"/api/v1/contacts/{created['id']}/interactions").json()
    assert tl["total"] == 2
    # Rodar de novo nao re-linka nada
    assert auth_a.post(
        "/api/v1/contacts/orphan-interactions/relink"
    ).json()["relinked"] == 0


# ============================================== C) leaderboard de cadastros


def test_leaderboard_counts_contacts_by_creator(auth_a):
    for i in range(3):
        auth_a.post(
            "/api/v1/contacts",
            json=_contact_payload(f"Contato {i}", f"(21) 9111{i:02d}-000{i}"),
        )
    lb = auth_a.get("/api/v1/contacts/leaderboard").json()
    assert len(lb) == 1
    assert lb[0]["full_name"] == "Owner alpha"
    assert lb[0]["count"] == 3


def test_leaderboard_excludes_soft_deleted_and_other_tenants(auth_a, auth_b):
    c = auth_a.post(
        "/api/v1/contacts", json=_contact_payload("Vai Sumir", "(21) 91234-5678"),
    ).json()
    auth_a.post("/api/v1/contacts", json=_contact_payload("Fica", "(21) 98765-4321"))
    auth_a.delete(f"/api/v1/contacts/{c['id']}")

    lb = auth_a.get("/api/v1/contacts/leaderboard").json()
    assert lb[0]["count"] == 1
    # Tenant B nao ve o ranking de A
    assert auth_b.get("/api/v1/contacts/leaderboard").json() == []


# ================================================= D) aging de demandas


def test_demands_open_older_than_days_filter(auth_a, db_session):
    contact = auth_a.post(
        "/api/v1/contacts", json=_contact_payload("Demandante", "(21) 93333-2222"),
    ).json()

    def _demand(title: str) -> dict:
        return auth_a.post("/api/v1/demands", json={
            "contact_id": contact["id"],
            "title": title,
            "description": "desc",
            "category": "Infraestrutura",
        }).json()

    d_new = _demand("Recente aberta")
    d_old_open = _demand("Parada ha 20 dias")
    d_old_resolved = _demand("Antiga mas resolvida")

    # Envelhece direto no DB (created_at nao e' input da API)
    from app.models.demand import Demand, DemandStatus
    old_dt = datetime.now(timezone.utc) - timedelta(days=20)
    for demand_id in (d_old_open["id"], d_old_resolved["id"]):
        row = db_session.get(Demand, uuid.UUID(demand_id))
        row.created_at = old_dt
    db_session.get(
        Demand, uuid.UUID(d_old_resolved["id"])
    ).status = DemandStatus.RESOLVED
    db_session.commit()

    res = auth_a.get("/api/v1/demands?open_older_than_days=15").json()
    ids = [d["id"] for d in res["items"]]
    assert d_old_open["id"] in ids          # aberta e velha: entra
    assert d_new["id"] not in ids           # aberta mas recente: fora
    assert d_old_resolved["id"] not in ids  # velha mas resolvida: fora
    assert res["total"] == 1


# ======================================== E) mutirao: filtros + interacao


def test_contacts_filter_by_neighborhood_and_type(auth_a):
    auth_a.post("/api/v1/contacts", json=_contact_payload(
        "Eleitor Centro", "(21) 90001-0001", neighborhood="Centro",
    ))
    auth_a.post("/api/v1/contacts", json=_contact_payload(
        "Lider Tijuca", "(21) 90002-0002", neighborhood="Tijuca", type="leader",
    ))

    r = auth_a.get("/api/v1/contacts?neighborhood=centro").json()
    assert r["total"] == 1
    assert r["items"][0]["full_name"] == "Eleitor Centro"

    r = auth_a.get("/api/v1/contacts?contact_type=leader").json()
    assert r["total"] == 1
    assert r["items"][0]["full_name"] == "Lider Tijuca"

    r = auth_a.get("/api/v1/contacts?neighborhood=tijuca&contact_type=leader").json()
    assert r["total"] == 1


def test_manual_interaction_created_and_listed(auth_a):
    c = auth_a.post(
        "/api/v1/contacts", json=_contact_payload("Maria Zap", "(21) 97777-0000"),
    ).json()

    r = auth_a.post(f"/api/v1/contacts/{c['id']}/interactions", json={
        "payload_data": {"template": "Boas-vindas", "mutirao_id": "m-2026-07-09"},
    })
    assert r.status_code == 201
    body = r.json()
    assert body["event_type"] == "mensagem_enviada"   # default do schema
    assert body["channel"] == "whatsapp"
    assert body["contact_id"] == c["id"]
    assert body["payload_data"]["template"] == "Boas-vindas"

    tl = auth_a.get(f"/api/v1/contacts/{c['id']}/interactions").json()
    assert tl["total"] == 1


def test_manual_interaction_cross_tenant_returns_404(auth_a, auth_b):
    c = auth_a.post(
        "/api/v1/contacts", json=_contact_payload("So do A", "(21) 96000-1000"),
    ).json()
    r = auth_b.post(f"/api/v1/contacts/{c['id']}/interactions", json={})
    assert r.status_code == 404
