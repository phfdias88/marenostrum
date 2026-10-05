"""
Cache-Control das rotas /tse: longo no historico, curto na apuracao.

O defeito que motivou: com `stale-while-revalidate=86400`, o navegador mostrava
a bancada de 45 minutos antes (22 eleitos) quando o banco ja tinha 30 — a copia
antiga e servida na hora e so a visita SEGUINTE traz o numero novo.
"""
from app.utils import apuracao


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_na_apuracao_a_resposta_dura_um_minuto_e_nao_serve_copia_velha(
    client, tenant_a, monkeypatch,
):
    _, _, token = tenant_a
    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", 2026)

    r = client.get("/api/v1/tse/parties", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "public, max-age=60"
    assert "stale-while-revalidate" not in r.headers["cache-control"]


def test_fora_da_apuracao_volta_o_cache_longo_do_historico(
    client, tenant_a, monkeypatch,
):
    _, _, token = tenant_a
    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", None)

    r = client.get("/api/v1/tse/parties", headers=_auth(token))
    assert r.headers["cache-control"] == (
        "public, max-age=300, stale-while-revalidate=86400"
    )


def test_rota_de_estado_mutavel_continua_sem_cache(client, tenant_a):
    """/sync muda a qualquer momento: nunca entrou na regra, e nao pode entrar."""
    _, _, token = tenant_a
    r = client.get("/api/v1/tse/sync", headers=_auth(token))
    assert r.headers.get("cache-control") == "no-store"
