"""
Testes do endpoint de webhook BotConversa.

Foco:
1. Validacao de secret (constant-time, per-tenant + fallback global)
2. Isolamento multi-tenant (secret de A nao autoriza webhook em B)
3. Orfas: payload com phone que nao existe no CRM
4. Tolerancia a payloads variados (extracao flexivel)
"""
import uuid

from app.models.interaction import Interaction


# ----------------------------------------------------- helpers/fixtures

# Fixture `tenant_a_with_secret` mora em conftest.py (compartilhada com
# os testes de multi_tenant da timeline).
SECRET_A = "secret-tenant-alpha-1234567890"


def _payload(phone: str | None = None, **extra) -> dict:
    base = {
        "event": "mensagem_recebida",
        "id": str(uuid.uuid4()),
        "message": {"text": "Oi, quero ajudar a campanha"},
    }
    if phone:
        base["phone"] = phone
    base.update(extra)
    return base


# ----------------------------------------------------------- security


def test_webhook_rejects_when_no_secret_configured(client, tenant_a):
    """Tenant sem webhook_secret + sem fallback global = 401."""
    tenant, _, _ = tenant_a
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json=_payload(phone="(32) 99999-1111"),
        headers={"X-Webhook-Secret": "qualquer-coisa"},
    )
    assert r.status_code == 401
    assert "configurado" in r.json()["message"].lower()


def test_webhook_rejects_wrong_secret(client, tenant_a_with_secret):
    tenant, _, _ = tenant_a_with_secret
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json=_payload(phone="(32) 99999-1111"),
        headers={"X-Webhook-Secret": "errado"},
    )
    assert r.status_code == 401


def test_webhook_rejects_missing_secret(client, tenant_a_with_secret):
    tenant, _, _ = tenant_a_with_secret
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json=_payload(phone="(32) 99999-1111"),
        # sem header nem query
    )
    assert r.status_code == 401


def test_webhook_accepts_secret_via_header(client, tenant_a_with_secret):
    tenant, _, _ = tenant_a_with_secret
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json=_payload(phone="(32) 99999-1111"),
        headers={"X-Webhook-Secret": SECRET_A},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "received"


def test_webhook_accepts_secret_via_query_param(client, tenant_a_with_secret):
    """Fallback: alguns provedores nao deixam custom header."""
    tenant, _, _ = tenant_a_with_secret
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}?secret={SECRET_A}",
        json=_payload(phone="(32) 99999-1111"),
    )
    assert r.status_code == 200


def test_webhook_unknown_tenant_returns_404(client, tenant_a_with_secret):
    """Tenant ID que nao existe — 404 mesmo com secret correto."""
    fake_id = uuid.uuid4()
    r = client.post(
        f"/api/v1/webhooks/botconversa/{fake_id}",
        json=_payload(phone="(32) 99999-1111"),
        headers={"X-Webhook-Secret": SECRET_A},
    )
    assert r.status_code == 404


# ----------------------------------------- isolamento multi-tenant ★


def test_secret_of_tenant_a_does_not_authorize_webhook_for_b(
    client, tenant_a_with_secret, tenant_b, db_session,
):
    """
    Bug catastrofico: B nao deve aceitar requests assinados com secret de A.
    Cada tenant valida APENAS contra seu proprio secret.
    """
    tenant_b_obj, _, _ = tenant_b
    tenant_b_obj.webhook_secret = "secret-tenant-bravo-9999"
    db_session.commit()

    # Atacante manda webhook pra B usando o secret de A
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant_b_obj.id}",
        json=_payload(phone="(32) 99999-1111"),
        headers={"X-Webhook-Secret": SECRET_A},
    )
    assert r.status_code == 401


# --------------------------------------------------- linking/orfas


def test_webhook_links_to_existing_contact_by_phone(
    client, auth_a, tenant_a_with_secret,
):
    tenant, _, _ = tenant_a_with_secret
    # Cria contato no CRM
    created = auth_a.post("/api/v1/contacts", json={
        "full_name": "João Silva",
        "phone": "(32) 99999-1234",
        "type": "voter",
    }).json()

    # Webhook chega com mesmo telefone
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json=_payload(phone="(32) 99999-1234"),
        headers={"X-Webhook-Secret": SECRET_A},
    )
    body = r.json()
    assert r.status_code == 200
    assert body["contact_matched"] is True
    assert body["contact_id"] == created["id"]


def test_webhook_saves_orphan_when_phone_not_in_crm(
    client, tenant_a_with_secret, db_session,
):
    tenant, _, _ = tenant_a_with_secret
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json=_payload(phone="(32) 99999-9999"),  # nao existe no CRM
        headers={"X-Webhook-Secret": SECRET_A},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["contact_matched"] is False
    assert body["contact_id"] is None

    # Conferindo no banco: interacao gravada com phone preservado
    inter = db_session.get(Interaction, uuid.UUID(body["interaction_id"]))
    assert inter is not None
    assert inter.phone == "(32) 99999-9999"
    assert inter.contact_id is None
    assert inter.tenant_id == tenant.id


def test_webhook_saves_even_without_phone_in_payload(
    client, tenant_a_with_secret, db_session,
):
    """Payload sem phone — salva mesmo assim, orfa total."""
    tenant, _, _ = tenant_a_with_secret
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json={"event": "fluxo_concluido", "data": {"flow": "boas_vindas"}},
        headers={"X-Webhook-Secret": SECRET_A},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["contact_matched"] is False

    inter = db_session.get(Interaction, uuid.UUID(body["interaction_id"]))
    assert inter.phone is None
    assert inter.event_type == "fluxo_concluido"


def test_webhook_extracts_phone_from_nested_subscriber(
    client, auth_a, tenant_a_with_secret,
):
    """BotConversa as vezes aninha em {subscriber: {phone: ...}}."""
    tenant, _, _ = tenant_a_with_secret
    auth_a.post("/api/v1/contacts", json={
        "full_name": "Maria", "phone": "(32) 88888-1234", "type": "voter",
    })

    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json={
            "event": "mensagem_recebida",
            "subscriber": {"phone": "(32) 88888-1234", "name": "Maria"},
        },
        headers={"X-Webhook-Secret": SECRET_A},
    )
    assert r.status_code == 200
    assert r.json()["contact_matched"] is True


# ----------------------------------------------------- payload storage


def test_webhook_stores_complete_payload(
    client, tenant_a_with_secret, db_session,
):
    """payload_data deve preservar TUDO que chegou — auditoria."""
    tenant, _, _ = tenant_a_with_secret
    payload = {
        "event": "mensagem_recebida",
        "phone": "(32) 99999-1234",
        "message": {"text": "qualquer coisa", "media_url": "https://x/img.jpg"},
        "campaign_id": "abc123",
        "custom_field": ["a", "b", "c"],
    }
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant.id}",
        json=payload,
        headers={"X-Webhook-Secret": SECRET_A},
    )
    inter = db_session.get(Interaction, uuid.UUID(r.json()["interaction_id"]))
    assert inter.payload_data == payload


# -------------------------------- isolamento multi-tenant em orfa


def test_orphan_interaction_does_not_leak_to_other_tenant(
    client, tenant_a_with_secret, tenant_b, db_session,
):
    """
    Mesmo telefone existe em B mas NAO em A. Webhook chega pra A —
    deve ficar orfa (B's contact NAO conta como match).
    """
    tenant_a, _, token_a = tenant_a_with_secret
    tenant_b_obj, _, token_b = tenant_b
    # Cria contato em B com o phone
    from app.models.contact import Contact, ContactType
    contact_b = Contact(
        tenant_id=tenant_b_obj.id,
        full_name="Contato do B",
        phone="(32) 77777-7777",
        type=ContactType.VOTER,
    )
    db_session.add(contact_b)
    db_session.commit()

    # Webhook chega pra A com aquele phone — NAO deve linkar com B
    r = client.post(
        f"/api/v1/webhooks/botconversa/{tenant_a.id}",
        json=_payload(phone="(32) 77777-7777"),
        headers={"X-Webhook-Secret": SECRET_A},
    )
    assert r.status_code == 200
    assert r.json()["contact_matched"] is False
    assert r.json()["contact_id"] is None
