"""Duas eleicoes lado a lado: a bancada que fica e a que entra, e a virada no mapa.

BANCADA. O Senado renova em partes: quem foi eleito ha quatro anos continua no
mandato, e a eleicao do ano preenche o resto. A tela mostra os dois grupos por
partido. Para a Camara nao existe "quem fica" — a casa inteira e renovada —,
entao o mesmo quadro vira "bancada eleita ha quatro anos x eleita agora".

Tres limites do dado, todos ditos na resposta em vez de escondidos:

  * O PARTIDO E O DA ELEICAO. O TSE nao publica troca de partido durante o
    mandato, nem suplente que assumiu. "No mandato" e quem foi ELEITO ha quatro
    anos, pelo partido de entao (levado ao sucessor legal, quando houve fusao).
    Por isso o numero pode diferir do que a imprensa mostra, que usa a filiacao
    de hoje.
  * ELEITO E SO QUEM O TSE PROCLAMOU. Na noite da apuracao a situacao chega UF
    por UF. Onde ainda nao chegou, os mais votados entram como "a frente" —
    separados dos eleitos, nunca somados a eles como se fossem oficiais.
  * NAO SE PROJETA DEPUTADO. A vaga proporcional depende do quociente do
    partido; "os mais votados" nao e uma previsao valida. Camara so mostra os
    proclamados.

VIRADA. Compara o partido mais votado de cada municipio em duas eleicoes. Le a
tabela materializada tse_winners_map (duas leituras por indice) e cruza em
memoria — o cruzamento direto em tse_vote_results custaria minutos.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.tse.candidate import Candidate
from app.models.tse.election import Election
from app.models.tse.party import Party
from app.utils.agg_cache import cached_agg
from app.utils.partidos import numero_sucessor

log = structlog.get_logger("marenostrum.services.eleicao_comparada")

SENADOR = 5
DEPUTADO_FEDERAL = 6
_CASAS = {SENADOR: "Senado Federal", DEPUTADO_FEDERAL: "Câmara dos Deputados"}

# Mandato de senador dura 8 anos e a eleicao e a cada 4: sempre ha uma turma
# no meio do mandato.
_INTERVALO = 4


def vagas_de_senador(ano: int) -> int:
    """Vagas de senador POR UF na eleicao do ano.

    O Senado renova um terco e dois tercos alternadamente: duas vagas por UF em
    2018 e 2026, uma em 2022 e 2030.
    """
    return 2 if (ano - 2018) % 8 == 0 else 1


def _eleito(situacao: str | None) -> bool:
    """Mesmo criterio de election_queries._eh_eleito_sql, no lado do Python.

    Por PREFIXO: "ELEITO" esta dentro de "NÃO ELEITO"."""
    s = (situacao or "").strip().upper()
    return s.startswith("ELEITO") or s == "MÉDIA"


def _derrotado(situacao: str | None) -> bool:
    s = (situacao or "").strip().upper()
    return s.startswith("NÃO ELEITO") or s.startswith("NAO ELEITO")


# ------------------------------------------------------------------ bancada

def get_bancada(db: Session, *, ano: int, cargo: int) -> dict[str, Any]:
    if cargo not in _CASAS:
        raise DomainError(
            "Bancada existe para senador (5) e deputado federal (6)."
        )
    return cached_agg(
        f"bancada:{ano}:{cargo}", lambda: _calcular_bancada(db, ano, cargo),
    )


def _candidatos(db: Session, ano: int, cargo: int):
    return db.execute(
        select(
            Candidate.state, Candidate.urn_name, Candidate.total_votes,
            Candidate.result_status, Party.number, Party.abbreviation,
        )
        .select_from(Candidate)
        .join(Election, Election.id == Candidate.election_id)
        .join(Party, Party.id == Candidate.party_id)
        .where(Election.year == ano, Candidate.office_code == cargo)
    ).all()


def _calcular_bancada(db: Session, ano: int, cargo: int) -> dict[str, Any]:
    anterior = ano - _INTERVALO
    senado = cargo == SENADOR

    do_ano = _candidatos(db, ano, cargo)
    de_antes = [r for r in _candidatos(db, anterior, cargo) if _eleito(r.result_status)]

    por_uf: dict[str, list] = defaultdict(list)
    for r in do_ano:
        por_uf[r.state].append(r)

    cadeiras_antes: dict[str, int] = defaultdict(int)
    for r in de_antes:
        cadeiras_antes[r.state] += 1

    eleitos: list = []
    a_frente: list = []
    ufs_pendentes: list[str] = []
    vagas = vagas_de_senador(ano) if senado else None
    em_disputa = 0
    for uf in sorted(por_uf):
        proclamados = [r for r in por_uf[uf] if _eleito(r.result_status)]
        eleitos.extend(proclamados)
        if not senado:
            # Deputado sai de uma vez por UF, quando o TSE fecha a conta do
            # quociente. UF fechada: as cadeiras sao as que ela elegeu. UF
            # aberta: vale o tamanho da bancada anterior, que e o melhor numero
            # disponivel ate o resultado sair.
            if proclamados:
                em_disputa += len(proclamados)
            else:
                ufs_pendentes.append(uf)
                em_disputa += cadeiras_antes[uf]
            continue
        em_disputa += vagas
        faltam = vagas - len(proclamados)
        if faltam <= 0:
            continue
        ufs_pendentes.append(uf)
        # Majoritario: enquanto o TSE nao proclama, os mais votados sao quem
        # esta na frente. Fica de fora quem ja consta como derrotado.
        na_disputa = sorted(
            (
                r for r in por_uf[uf]
                if not _eleito(r.result_status)
                and not _derrotado(r.result_status)
                and (r.total_votes or 0) > 0
            ),
            key=lambda r: (-(r.total_votes or 0), r.urn_name or ""),
        )
        a_frente.extend(na_disputa[:faltam])

    # A sigla que aparece e a da eleicao mais recente: um senador eleito pelo
    # PSC em 2022 esta hoje na bancada do Podemos, que o incorporou.
    sigla_de: dict[int, str] = {}
    for r in de_antes:
        sigla_de.setdefault(numero_sucessor(r.number, anterior), r.abbreviation)
    for r in do_ano:
        sigla_de[numero_sucessor(r.number, ano)] = r.abbreviation

    partidos: dict[int, dict[str, Any]] = {}
    cadeiras: list[dict[str, Any]] = []

    def _contar(linhas, ano_da_linha: int, campo: str) -> None:
        for r in linhas:
            numero = numero_sucessor(r.number, ano_da_linha)
            p = partidos.setdefault(numero, {
                "numero": numero, "sigla": sigla_de[numero],
                "antes": 0, "eleitos": 0, "a_frente": 0,
            })
            p[campo] += 1
            cadeiras.append({
                "uf": r.state, "nome": r.urn_name, "numero": numero,
                "sigla": sigla_de[numero], "situacao": campo,
                "votos": int(r.total_votes or 0),
            })

    _contar(de_antes, anterior, "antes")
    _contar(eleitos, ano, "eleitos")
    _contar(a_frente, ano, "a_frente")

    for p in partidos.values():
        # No Senado quem estava continua, entao soma. Na Camara a bancada
        # antiga e SUBSTITUIDA: somar daria uma casa com o dobro do tamanho.
        entrando = p["eleitos"] + p["a_frente"]
        p["total"] = p["antes"] + entrando if senado else entrando

    lista = sorted(
        partidos.values(),
        key=lambda p: (-p["total"], -p["eleitos"], -p["antes"], p["sigla"]),
    )

    if senado:
        observacao = (
            f"'No mandato' são os senadores eleitos em {anterior}, pelo partido "
            "daquela eleição: o TSE não publica troca de partido durante o "
            "mandato nem suplente que assumiu, então o número pode diferir do "
            "que usa a filiação de hoje. 'À frente' são os mais votados nas UFs "
            "onde o TSE ainda não proclamou o resultado — não são eleitos."
        )
    else:
        observacao = (
            f"A Câmara é renovada por inteiro: a coluna de {anterior} é a "
            "bancada eleita naquele ano, não gente que continua. Só entram como "
            "eleitos os deputados que o TSE já proclamou; vaga proporcional "
            "depende do quociente do partido e não se projeta pelos mais votados."
        )
        if ufs_pendentes:
            observacao += (
                " Nas UFs ainda sem resultado, o total de cadeiras considera o "
                f"mesmo número de {anterior}."
            )

    log.info(
        "bancada_pronta", ano=ano, cargo=cargo, antes=len(de_antes),
        eleitos=len(eleitos), a_frente=len(a_frente), pendentes=len(ufs_pendentes),
    )
    return {
        "ano": ano,
        "ano_anterior": anterior,
        "cargo": cargo,
        "casa": _CASAS[cargo],
        "modo": "soma" if senado else "troca",
        "vagas_por_uf": vagas,
        "em_disputa": em_disputa,
        "antes": len(de_antes),
        "eleitos": len(eleitos),
        "a_frente": len(a_frente),
        "ufs": len(por_uf),
        "ufs_pendentes": ufs_pendentes,
        "observacao": observacao,
        "partidos": lista,
        "cadeiras": cadeiras,
    }


# ------------------------------------------------------------------- virada

def get_virada(db: Session, *, cargo: int, de: int, para: int) -> dict[str, Any]:
    if de >= para:
        raise DomainError("O ano de partida precisa ser anterior ao de chegada.")
    return cached_agg(
        f"virada:{cargo}:{de}:{para}", lambda: _calcular_virada(db, cargo, de, para),
    )


_VENCEDORES = text("""
    SELECT municipality_id, municipality, state, latitude, longitude,
           party_number, party_abbr, urn_name, votes
    FROM tse_winners_map
    WHERE year = :ano AND office_code = :cargo AND latitude IS NOT NULL
""")


def _calcular_virada(db: Session, cargo: int, de: int, para: int) -> dict[str, Any]:
    antes = db.execute(_VENCEDORES, {"ano": de, "cargo": cargo}).mappings().all()
    depois = db.execute(_VENCEDORES, {"ano": para, "cargo": cargo}).mappings().all()
    resultado = cruzar_vencedores(antes, depois, de, para)
    resultado.update({"cargo": cargo, "de": de, "para": para})
    log.info(
        "virada_pronta", cargo=cargo, de=de, para=para,
        municipios=len(resultado["pontos"]), viraram=resultado["viraram"],
    )
    return resultado


def cruzar_vencedores(antes, depois, de: int, para: int) -> dict[str, Any]:
    """Junta o vencedor de cada municipio nas duas eleicoes.

    So entra municipio que tem vencedor nos DOIS anos: sem um dos lados nao ha
    o que comparar, e pinta-lo como "virou" seria inventar."""
    antigo = {str(r["municipality_id"]): r for r in antes}
    pontos: list[dict[str, Any]] = []
    transicoes: dict[str, dict[str, Any]] = {}
    viraram = 0

    for r in depois:
        mid = str(r["municipality_id"])
        a = antigo.get(mid)
        if a is None:
            continue
        num_a = numero_sucessor(int(a["party_number"]), de)
        num_d = numero_sucessor(int(r["party_number"]), para)
        virou = num_a != num_d
        viraram += virou
        chave = f"{num_a}>{num_d}"
        t = transicoes.setdefault(chave, {
            "chave": chave, "virou": virou, "municipios": 0,
            "de": {"numero": num_a, "sigla": a["party_abbr"]},
            "para": {"numero": num_d, "sigla": r["party_abbr"]},
        })
        t["municipios"] += 1
        pontos.append({
            "municipality_id": mid,
            "name": r["municipality"],
            "state": r["state"],
            "lat": float(r["latitude"]),
            "lng": float(r["longitude"]),
            "transicao": chave,
            "virou": virou,
            "antes": {
                "party_number": num_a, "party_abbreviation": a["party_abbr"],
                "winner_name": a["urn_name"], "votes": int(a["votes"]),
            },
            "depois": {
                "party_number": num_d, "party_abbreviation": r["party_abbr"],
                "winner_name": r["urn_name"], "votes": int(r["votes"]),
            },
        })

    return {
        "municipios": len(pontos),
        "viraram": viraram,
        "mantiveram": len(pontos) - viraram,
        # Municipios com vencedor em so um dos anos (carga incompleta de um
        # deles). Fora do mapa, mas contados para o numero nao sumir calado.
        "sem_comparacao": len(depois) - len(pontos),
        "transicoes": sorted(
            transicoes.values(), key=lambda t: (-t["municipios"], t["chave"]),
        ),
        "pontos": pontos,
    }
