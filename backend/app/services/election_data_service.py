"""Agregacao de votos por escopo de eleicao (municipio / bairro).

Existe porque quem monta painel precisa do dado JA somado, e as rotas antigas
so respondem por candidato (`/candidates/{id}/by-neighborhood`) ou por um bairro
fixo (`/neighborhoods/ranking`). Aqui a pergunta e outra: "dado uf + ano + cargo
+ turno, como os votos se distribuem no territorio?".

DUAS FONTES, ESCOLHIDAS PELO ESCOPO — nao e detalhe de implementacao, muda o que
a resposta significa:

  sem municipio  -> soma por MUNICIPIO, de `tse_vote_results`.
                    Cobre 2014-2024, Brasil inteiro, e o numero e exato.

  com municipio  -> soma por BAIRRO, de `tse_section_votes` x `tse_voting_places`.
                    So existe onde importamos secao: 2024 (Brasil) e
                    2018/2020/2022 (so RJ). Fora disso a lista volta vazia.

TURNO NAO E FILTRO — E ARMADILHA. No TSE, quem vai ao 2o turno tem a
candidatura registrada numa eleicao com `round=2`, mas os votos gravados ali
sao os do PRIMEIRO turno. Conferido em producao: Sao Paulo 2024 tem 8
candidatos em round=1 (2.531.785 votos) e Nunes+Boulos em round=2 com
1.801.139+1.776.127 = 3.577.266 — os numeros de 1o turno deles. Somando os
dois registros: 6.109.051, que e o total real do 1o turno. Mesmo padrao em
Fortaleza, Curitiba e na presidencial de 2022 (Bolsonaro em round=2 com
51.072.345, o total dele no 1o turno).

Consequencia: filtrar `round == 1` derruba os dois mais votados de toda cidade
que teve segundo turno. Por isso este servico NAO filtra por turno e soma os
dois registros. Voto de 2o turno nao existe na base.

RESSALVA DE QUALIDADE (agosto/2026): o importador grava local de votacao com
chave (ano, municipio, numero do local), mas no TSE esse numero so e unico
DENTRO da zona eleitoral. Em cidade com mais de uma zona, locais distintos
colidem e viram um so — o total do municipio continua certo (os votos sao
somados), mas a atribuicao de BAIRRO fica errada. Enquanto isso nao for
reimportado com a zona na chave, trate a quebra por bairro como aproximacao.
Ver `dados_confiaveis` na resposta.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models.tse.candidate import Candidate
from app.models.tse.election import Election
from app.models.tse.municipality import Municipality
from app.models.tse.section_vote import TseSectionVote
from app.models.tse.vote_result import VoteResult
from app.models.tse.voting_place import TseVotingPlace
from app.utils.agg_cache import cached_agg
from app.utils.locais_fundidos import MUNICIPIOS_COM_LOCAIS_FUNDIDOS

log = structlog.get_logger("marenostrum.services.election_data")

# Anos com voto por SECAO importado. Fora daqui a quebra por bairro nao existe
# (nao e erro: a resposta volta vazia com `cobertura` explicando).
ANOS_COM_BAIRRO = (2018, 2020, 2022, 2024)

# Teto de tempo por consulta. O nginx corta em 60s mas NAO cancela a query, entao
# quem recarrega a pagina empilha agregacao em cima de 1 vCPU. Cortar no banco.
TIMEOUT_MS = 25_000


class AgregacaoIndisponivelError(DomainError):
    """A consulta nao completou (timeout/banco). 503, nao 500: e transitorio e o
    caminho de saida e refinar o escopo, nao abrir chamado."""

    status_code = 503
    code = "aggregation_unavailable"


def get_aggregated_votes(
    db: Session,
    *,
    uf: str,
    ano: int,
    cargo: int,
    municipio: UUID | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Devolve os votos somados por municipio (ou por bairro, se `municipio`).

    O resultado e cacheado por 4h: sao dados historicos, nao mudam entre
    requisicoes, e a consulta custa segundos.
    """
    uf = (uf or "").strip().upper()
    chave = f"agg_votos:{uf}:{ano}:{cargo}:{municipio}:{limit}"

    log.info(
        "agregacao_pedida",
        uf=uf, ano=ano, cargo=cargo,
        municipio=str(municipio) if municipio else None,
    )

    return cached_agg(
        chave,
        lambda: _calcular(db, uf, ano, cargo, municipio, limit),
    )


def _calcular(
    db: Session,
    uf: str,
    ano: int,
    cargo: int,
    municipio: UUID | None,
    limit: int,
) -> dict[str, Any]:
    try:
        # Teto local: some no fim da transacao, nao vaza pra conexao do pool.
        # So no Postgres — a suite roda em SQLite, que nao tem set_config e
        # derrubaria a rota inteira com "no such function".
        if getattr(getattr(db.bind, "dialect", None), "name", "") == "postgresql":
            db.execute(select(func.set_config(
                "statement_timeout", str(TIMEOUT_MS), True,
            )))

        if municipio is not None:
            itens, escopo, cobertura, confiavel = _por_bairro(
                db, ano, cargo, municipio, limit,
            )
        else:
            itens, escopo, cobertura, confiavel = _por_municipio(
                db, uf, ano, cargo, limit,
            )

    except OperationalError as exc:
        # statement_timeout estoura aqui. Escopo largo demais pro hardware.
        log.warning(
            "agregacao_estourou_tempo",
            uf=uf, ano=ano, cargo=cargo,
            municipio=str(municipio) if municipio else None,
            erro=str(exc)[:200],
        )
        raise AgregacaoIndisponivelError(
            "A consulta demorou demais. Informe o municipio para reduzir o "
            "escopo, ou tente de novo em instantes."
        ) from exc

    except SQLAlchemyError as exc:
        log.error(
            "agregacao_falhou",
            uf=uf, ano=ano, cargo=cargo, erro=str(exc)[:200],
        )
        raise AgregacaoIndisponivelError(
            "Nao foi possivel agregar os votos agora."
        ) from exc

    total = sum(i["total_votos"] for i in itens)
    log.info(
        "agregacao_pronta",
        uf=uf, ano=ano, cargo=cargo, escopo=escopo,
        linhas=len(itens), total_votos=total,
    )

    return {
        "escopo": escopo,
        "uf": uf,
        "ano": ano,
        "cargo": cargo,
        "total_votos": total,
        "cobertura": cobertura,
        "dados_confiaveis": confiavel,
        "itens": itens,
    }


def _por_municipio(
    db: Session, uf: str, ano: int, cargo: int, limit: int,
) -> tuple[list[dict[str, Any]], str, str, bool]:
    """Soma por municipio, de tse_vote_results. Rapido e exato."""
    stmt = (
        select(
            Municipality.name.label("municipio"),
            Municipality.id.label("municipio_id"),
            func.sum(VoteResult.votes).label("total"),
        )
        .select_from(VoteResult)
        .join(Candidate, Candidate.id == VoteResult.candidate_id)
        .join(Election, Election.id == Candidate.election_id)
        .join(Municipality, Municipality.id == VoteResult.municipality_id)
        .where(
            Election.year == ano,
            # SEM filtro de round: ver a nota no topo — os dois finalistas ficam
            # num registro round=2 carregando votos de 1o turno.
            Candidate.office_code == cargo,
            # Presidente concorre com state='BR': o recorte territorial tem de
            # sair do municipio, nao do candidato (mesmo criterio do
            # /election-results).
            Municipality.state == uf if cargo == 1 else Candidate.state == uf,
        )
        .group_by(Municipality.id, Municipality.name)
        .order_by(func.sum(VoteResult.votes).desc())
        .limit(limit)
    )

    itens = [
        {
            "municipio": r.municipio,
            "municipio_id": str(r.municipio_id),
            "bairro": None,
            "total_votos": int(r.total or 0),
        }
        for r in db.execute(stmt)
    ]
    return (
        itens,
        "municipio",
        "Voto por municipio: 2014 a 2024, Brasil. Numeros de 1o turno — a base "
        "nao tem votacao de 2o turno; quem foi ao 2o turno entra com os votos "
        "do 1o.",
        True,
    )


def _por_bairro(
    db: Session, ano: int, cargo: int, municipio: UUID, limit: int,
) -> tuple[list[dict[str, Any]], str, str, bool]:
    """Soma por bairro dentro de um municipio, de tse_section_votes.

    A ORDEM IMPORTA: partimos dos locais do municipio (dezenas) e so entao
    tocamos em tse_section_votes pelo indice (voting_place_id, votes). Filtrar
    pelo municipio depois de juntar as secoes leva o planejador a varrer voto a
    voto — medido em producao: 30,5s daquele jeito, 1,8s deste.
    """
    muni = db.get(Municipality, municipio)
    if muni is None:
        raise NotFoundError("Municipio nao encontrado")

    confiavel = _bairro_confiavel(db, muni, ano)

    if ano not in ANOS_COM_BAIRRO:
        return [], "bairro", _cobertura_bairro(confiavel), True

    locais = (
        select(
            TseVotingPlace.id.label("local_id"),
            func.coalesce(
                func.nullif(func.trim(TseVotingPlace.neighborhood), ""),
                "(Sem bairro)",
            ).label("bairro"),
        )
        .where(
            TseVotingPlace.municipality_id == municipio,
            TseVotingPlace.year == ano,
        )
        .cte("locais")
    )

    stmt = (
        select(
            locais.c.bairro,
            func.sum(TseSectionVote.votes).label("total"),
        )
        .select_from(locais)
        .join(TseSectionVote, TseSectionVote.voting_place_id == locais.c.local_id)
        .join(Candidate, Candidate.id == TseSectionVote.candidate_id)
        .join(Election, Election.id == Candidate.election_id)
        .where(
            Election.year == ano,
            Candidate.office_code == cargo,
        )
        .group_by(locais.c.bairro)
        .order_by(func.sum(TseSectionVote.votes).desc())
        .limit(limit)
    )

    itens = [
        {
            "municipio": muni.name,
            "municipio_id": str(muni.id),
            "bairro": r.bairro,
            "total_votos": int(r.total or 0),
        }
        for r in db.execute(stmt)
    ]
    return itens, "bairro", _cobertura_bairro(confiavel), confiavel


def _bairro_confiavel(db: Session, muni: Municipality, ano: int) -> bool:
    """A quebra por bairro deste municipio pode ser levada a serio?

    Duas fontes, nesta ordem:
      1. se os locais do ano ja tem `zone` preenchido, o municipio foi
         reimportado com a zona na chave — confia no dado, nao na lista;
      2. senao, cai na lista apurada no arquivo do TSE: so 187 municipios de
         5.569 tiveram locais fundidos. Nos outros 96,6% nada se perdeu, e
         dizer "aproximado" ali seria desconfianca sem motivo.
    """
    reimportado = db.execute(
        select(func.count()).select_from(TseVotingPlace).where(
            TseVotingPlace.municipality_id == muni.id,
            TseVotingPlace.year == ano,
            TseVotingPlace.zone.is_not(None),
        )
    ).scalar() or 0
    if reimportado:
        return True
    return muni.tse_code not in MUNICIPIOS_COM_LOCAIS_FUNDIDOS


def _cobertura_bairro(confiavel: bool = True) -> str:
    base = (
        "Voto por bairro vem das secoes eleitorais: 2024 (Brasil) e "
        "2018/2020/2022 (somente RJ). Fora desse recorte a lista volta vazia."
    )
    if confiavel:
        return base + " Neste municipio cada local de votacao esta separado"                       " corretamente, entao a divisao por bairro pode ser usada."
    return base + (
        " NESTE MUNICIPIO a divisao por bairro e aproximada: locais de zonas "
        "eleitorais diferentes com o mesmo numero foram gravados como um so, "
        "entao parte dos votos aparece no bairro do vizinho. O total do "
        "municipio continua correto. Some depois de reimportar os locais com "
        "a zona na chave."
    )


__all__ = ["get_aggregated_votes", "AgregacaoIndisponivelError", "ANOS_COM_BAIRRO"]
