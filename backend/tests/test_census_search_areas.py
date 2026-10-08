"""
/census/search-areas — a busca de bairros da busca global.

O indice de areas e montado sob demanda e fica em memoria. Em 06/10/2026 ele
estava fora do cache quando tres pessoas digitavam na busca: cada tecla virou
uma montagem (varredura de 468 mil setores + uma copia do resultado), a API
passou do limite de memoria e o container foi morto. Os testes fixam que a
montagem acontece UMA vez, por mais pedidos que cheguem juntos.
"""
import threading
import time

import pytest

from app.controllers import census
from app.models.census import Setor
from app.utils.agg_cache import agg_get


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class _SessaoFalsa:
    def rollback(self) -> None:
        pass


def _setor(n: int, *, mun="3304557", nm_mun="Rio de Janeiro", bairro="", dist=""):
    return Setor(cd_setor=f"33045570000{n:04d}", cd_mun=mun, nm_mun=nm_mun,
                     nm_bairro=bairro, nm_dist=dist)


def test_pedidos_simultaneos_montam_o_indice_uma_vez(monkeypatch):
    montagens = []

    def montar_devagar(db):
        montagens.append(1)
        time.sleep(0.3)             # o tempo em que os outros pedidos chegam
        return [{"nome": "Centro", "_key": "centro"}]

    monkeypatch.setattr(census, "_montar_indice_de_areas", montar_devagar)
    recebidos = []

    def pedir():
        recebidos.append(census._indice_de_areas(_SessaoFalsa()))

    pedidos = [threading.Thread(target=pedir) for _ in range(8)]
    for p in pedidos:
        p.start()
    for p in pedidos:
        p.join(timeout=10)

    assert len(montagens) == 1
    assert len(recebidos) == 8
    assert all(r is recebidos[0] for r in recebidos)   # a mesma lista, nao 8 copias


def test_montagem_que_falha_nao_trava_os_proximos(monkeypatch):
    def falhar(db):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(census, "_montar_indice_de_areas", falhar)
    with pytest.raises(RuntimeError):
        census._indice_de_areas(_SessaoFalsa())

    monkeypatch.setattr(census, "_montar_indice_de_areas", lambda db: [{"nome": "X", "_key": "x"}])
    assert census._indice_de_areas(_SessaoFalsa()) == [{"nome": "X", "_key": "x"}]


def test_quem_espera_solta_a_conexao_antes_da_fila(monkeypatch):
    """Na fila da montagem o pedido nao pode segurar conexao do pool."""
    ordem = []

    class Sessao:
        def rollback(self):
            ordem.append("rollback")

    def montar(db):
        ordem.append("montar")
        return []

    monkeypatch.setattr(census, "_montar_indice_de_areas", montar)
    census._indice_de_areas(Sessao())

    assert ordem == ["rollback", "montar"]


def test_indice_em_cache_nao_toca_no_banco(monkeypatch):
    monkeypatch.setattr(census, "_montar_indice_de_areas", lambda db: [{"nome": "A", "_key": "a"}])
    census._indice_de_areas(_SessaoFalsa())

    def nao_pode(db):
        raise AssertionError("montou de novo com o indice no cache")

    monkeypatch.setattr(census, "_montar_indice_de_areas", nao_pode)

    class SessaoQueNaoPodeSerUsada:
        def rollback(self):
            raise AssertionError("rollback com o indice no cache")

    assert census._indice_de_areas(SessaoQueNaoPodeSerUsada()) == [{"nome": "A", "_key": "a"}]


def test_busca_devolve_bairro_e_distrito_do_banco(client, tenant_a, db_session):
    _, user, token = tenant_a
    user.census_enabled = True
    db_session.add_all([
        _setor(1, bairro="Copacabana"),
        _setor(2, bairro="Copacabana"),                       # mesmo bairro, outro setor
        _setor(3, mun="3303302", nm_mun="Niterói", dist="Copa do Mundo"),
        _setor(4, bairro="Tijuca"),
        _setor(5),                                            # sem bairro nem distrito
    ])
    db_session.commit()

    r = client.get("/api/v1/census/search-areas?q=copa", headers=_auth(token))

    assert r.status_code == 200, r.text
    assert [(i["nome"], i["kind"], i["nm_mun"], i["uf"]) for i in r.json()] == [
        ("Copacabana", "Bairro", "Rio de Janeiro", "RJ"),     # um so, apesar dos 2 setores
        ("Copa do Mundo", "Distrito", "Niterói", "RJ"),
    ]
    assert "_key" not in r.json()[0]
    # Ficou no cache: a proxima tecla nao varre os setores de novo.
    assert len(agg_get(census._AREA_INDEX_KEY)) == 3


def test_sem_o_modulo_censo_nao_devolve_nada_nem_monta_indice(client, tenant_a, db_session):
    _, user, token = tenant_a
    user.census_enabled = False
    db_session.add(_setor(1, bairro="Copacabana"))
    db_session.commit()

    r = client.get("/api/v1/census/search-areas?q=copa", headers=_auth(token))

    assert r.status_code == 200 and r.json() == []
    assert agg_get(census._AREA_INDEX_KEY) is None
