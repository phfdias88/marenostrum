"""
POST /tse/ingest/cache-clear — o aviso que a captura ao vivo da a API.

Depois do consolidado do 1o turno, ANO_EM_APURACAO volta a None; a captura do
2o turno continua avisando a API a cada passada. Sem o `ano` explicito, cada
passada esvaziaria o cache INTEIRO e as telas pesadas dos anos fechados
recalculariam do zero a noite toda.
"""
from app.utils import agg_cache, apuracao


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _encher():
    agg_cache.clear_agg_cache()
    for chave in ("party_perf:2026:1:", "counts:None", "party_perf:2022:6:", "census:area_index"):
        agg_cache.agg_set(chave, {"x": 1})


def test_com_ano_limpa_so_o_que_o_ano_pode_ter_mudado(client, tenant_a, monkeypatch):
    _, _, token = tenant_a
    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", None)
    _encher()

    r = client.post("/api/v1/tse/ingest/cache-clear?ano=2026", headers=_auth(token))

    assert r.status_code == 200, r.text
    assert set(agg_cache._store) == {"party_perf:2022:6:", "census:area_index"}


def test_sem_ano_e_sem_apuracao_limpa_tudo(client, tenant_a, monkeypatch):
    _, _, token = tenant_a
    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", None)
    _encher()

    r = client.post("/api/v1/tse/ingest/cache-clear", headers=_auth(token))

    assert r.status_code == 200, r.text
    assert agg_cache._store == {}


def test_everything_ignora_o_ano(client, tenant_a, monkeypatch):
    _, _, token = tenant_a
    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", 2026)
    _encher()

    r = client.post("/api/v1/tse/ingest/cache-clear?ano=2026&everything=true",
                    headers=_auth(token))

    assert r.status_code == 200, r.text
    assert agg_cache._store == {}
