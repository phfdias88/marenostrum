"""
Chave de API: acesso programatico somente leitura.

O que estes testes protegem, em ordem de gravidade se quebrar:
1. A chave NAO escreve  — senao um token de integracao vira poder de alterar.
2. A chave NAO atravessa clientes — o isolamento e a promessa central do SaaS.
3. Revogada/vencida para de valer NA HORA — senao nao ha como cortar acesso.
4. O valor da chave nao fica no banco — vazou o dump, ninguem entra.
"""
from datetime import datetime, timedelta, timezone

from app.core.dependencies import hash_api_key
from app.models.api_key import ApiKey


def _cria_chave(db, tenant_id, **kw) -> str:
    """Cria a chave e devolve o valor cru (como o endpoint faz uma vez)."""
    raw = kw.pop("raw", "mn_live_chave_de_teste_1234567890")
    db.add(ApiKey(
        tenant_id=tenant_id,
        name=kw.pop("name", "teste"),
        key_hash=hash_api_key(raw),
        prefix=raw[:16],
        scopes="read",
        **kw,
    ))
    db.commit()
    return raw


def test_chave_le_dados(client, tenant_a, db_session):
    tenant, _user, _tok = tenant_a
    raw = _cria_chave(db_session, tenant.id)

    r = client.get("/api/v1/contacts", headers={"X-API-Key": raw})
    assert r.status_code == 200, r.text


def test_chave_nao_escreve(client, tenant_a, db_session):
    """A trava mora no portao (dependencia), nao em cada rota: rota nova
    nasce protegida sem ninguem precisar lembrar."""
    tenant, _user, _tok = tenant_a
    raw = _cria_chave(db_session, tenant.id, raw="mn_live_somente_leitura_abc")

    r = client.post(
        "/api/v1/contacts",
        headers={"X-API-Key": raw},
        json={"full_name": "Fulano", "contact_type": "eleitor"},
    )
    assert r.status_code == 403
    assert "somente leitura" in r.json().get("detail", "").lower()


def test_chave_nao_enxerga_outro_cliente(client, tenant_a, tenant_b, db_session):
    """O dado que a chave devolve e o do tenant DELA — nunca o do vizinho."""
    tenant_um, _u1, _t1 = tenant_a
    tenant_dois, _u2, tok_dois = tenant_b

    # contato criado no tenant B, pelo caminho normal
    r = client.post(
        "/api/v1/contacts",
        headers={"Authorization": f"Bearer {tok_dois}"},
        json={"full_name": "Contato do vizinho", "contact_type": "eleitor"},
    )
    assert r.status_code in (200, 201), r.text

    # a chave do tenant A nao pode ver esse contato
    raw = _cria_chave(db_session, tenant_um.id, raw="mn_live_isolamento_teste_x")
    r = client.get("/api/v1/contacts", headers={"X-API-Key": raw})
    assert r.status_code == 200
    nomes = [c["full_name"] for c in r.json()["items"]]
    assert "Contato do vizinho" not in nomes


def test_chave_revogada_para_de_valer(client, tenant_a, db_session):
    tenant, _user, _tok = tenant_a
    raw = _cria_chave(db_session, tenant.id, raw="mn_live_revogada_teste_999",
                      revoked_at=datetime.now(timezone.utc))

    r = client.get("/api/v1/contacts", headers={"X-API-Key": raw})
    assert r.status_code == 401


def test_chave_vencida_para_de_valer(client, tenant_a, db_session):
    tenant, _user, _tok = tenant_a
    raw = _cria_chave(db_session, tenant.id, raw="mn_live_vencida_teste_888",
                      expires_at=datetime.now(timezone.utc) - timedelta(days=1))

    r = client.get("/api/v1/contacts", headers={"X-API-Key": raw})
    assert r.status_code == 401


def test_chave_inexistente_e_recusada(client, tenant_a):
    r = client.get("/api/v1/contacts", headers={"X-API-Key": "mn_live_nao_existe"})
    assert r.status_code == 401


def test_banco_guarda_hash_e_nao_a_chave(db_session, tenant_a):
    """Se o dump vazar, a chave nao pode estar la em texto."""
    tenant, _user, _tok = tenant_a
    raw = _cria_chave(db_session, tenant.id, raw="mn_live_segredo_absoluto_77")

    linha = db_session.query(ApiKey).filter(
        ApiKey.key_hash == hash_api_key(raw)
    ).one()
    assert linha.key_hash != raw
    assert len(linha.key_hash) == 64          # SHA-256 em hex
    assert raw not in linha.prefix            # prefixo nao reconstroi a chave
    assert linha.prefix == raw[:16]


def test_login_normal_continua_funcionando(client, tenant_a):
    """A troca de autenticacao nao pode ter quebrado o caminho humano."""
    _tenant, _user, tok = tenant_a
    r = client.get("/api/v1/contacts", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def test_sem_credencial_nenhuma_e_401(client):
    r = client.get("/api/v1/contacts")
    assert r.status_code == 401
