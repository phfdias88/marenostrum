"""Consultas de eleicao para quem consome a API por fora da tela.

Duas perguntas pedidas pelo socio, que nenhuma rota respondia:

  1. QUEM FOI ELEITO (ou nao) numa eleicao — por ano, UF e, opcionalmente,
     municipio (pelo NOME, nao por id).
  2. O PERFIL DO ELEITORADO daquele recorte — sexo, faixa etaria,
     escolaridade, estado civil e cor/raca.

Tres armadilhas ficam resolvidas aqui, e e por isso que estas funcoes moram no
servidor em vez de no cliente:

TURNO NAO E FILTRO. `result_status` ja carrega o resultado FINAL. Conferido em
producao: Evandro Leitao consta ELEITO no registro de 2o turno de Fortaleza,
embora os votos gravados ali sejam os do 1o turno. Filtrar por turno so
esconderia gente.

"ELEITO" NAO E UM VALOR SO. O TSE usa ELEITO, ELEITO POR QP e ELEITO POR MEDIA
(e, ate 2010, so "MEDIA"). Filtrar `= 'ELEITO'` devolve 21.353 candidatos e
perde 178.913 — quase todo vereador e deputado entra por quociente partidario
ou por media. E usar LIKE '%ELEITO%' e pior ainda: casa com 'NAO ELEITO'. O
criterio certo e PREFIXO.

CANDIDATO NAO TEM MUNICIPIO. A tabela so guarda a UF; o vinculo territorial vem
do voto (`tse_vote_results`). Para cargo municipal isso equivale a "concorreu
ali", que e o que o consumidor espera.
"""
from __future__ import annotations

import unicodedata
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.tse.candidate import Candidate
from app.models.tse.election import Election
from app.models.tse.electorate import MunicipalityElectorate
from app.models.tse.municipality import Municipality
from app.models.tse.party import Party
from app.models.tse.vote_result import VoteResult
from app.utils.agg_cache import cached_agg

log = structlog.get_logger("marenostrum.services.election_queries")

# Como reconhecer "eleito". O teste e por PREFIXO — "ELEITO" esta dentro de
# "NAO ELEITO", entao comparar por conter traria os derrotados junto. Prefixo
# tambem cobre variante nova que o TSE venha a criar, coisa que uma lista fixa
# nao faria. "MEDIA" sozinho e o jeito antigo (ate 2010) de dizer eleito por
# media: 622 candidaturas, todas de cargo proporcional.
_PREFIXO_ELEITO = "ELEITO"
_ELEITO_ANTIGO = "MÉDIA"


def _eh_eleito_sql():
    """Predicado SQL de eleito. Mesmo criterio usado no resto do backend
    (controllers/tse.py:501), mais o 'MEDIA' antigo que aquele filtro perde."""
    return Candidate.result_status.like(f"{_PREFIXO_ELEITO}%") | (
        Candidate.result_status == _ELEITO_ANTIGO
    )

# Anos com perfil de eleitorado carregado. Fora daqui a resposta volta vazia,
# com `observacao` explicando — nao e erro.
ANOS_COM_ELEITORADO = (2024,)


def _sem_acento(texto: str) -> str:
    """Tira acento no lado do Python, pro texto digitado casar com o banco."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _achar_municipio(db: Session, uf: str, nome: str) -> Municipality:
    """Municipio pelo NOME, ignorando caixa E acento.

    Quem consome digita NITEROI, nao NITERÓI — exigir o acento devolveria 404
    num municipio que existe. No Postgres usamos f_unaccent (mesmo padrao do
    censo, controllers/census.py:773); no SQLite dos testes a comparacao simples
    basta, porque os nomes de teste sao ASCII.
    """
    procurado = _sem_acento(nome).upper()
    coluna = func.upper(Municipality.name)
    if getattr(getattr(db.bind, "dialect", None), "name", "") == "postgresql":
        coluna = func.upper(func.public.f_unaccent(Municipality.name))

    alvo = db.execute(
        select(Municipality).where(
            Municipality.state == uf,
            coluna == procurado,
        )
    ).scalars().first()
    if alvo is None:
        raise NotFoundError(f"Municipio '{nome}' nao encontrado em {uf}.")
    return alvo


# ------------------------------------------------------------------ eleitos

def get_elected(
    db: Session,
    *,
    ano: int,
    uf: str,
    municipio: str | None = None,
    cargo: int | None = None,
    eleito: bool = True,
    meios_contato: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    """Quem foi eleito (ou nao) numa eleicao. Sem municipio, a UF inteira."""
    uf = (uf or "").strip().upper()
    mun = (municipio or "").strip().upper() or None
    chave = f"eleitos:{ano}:{uf}:{mun}:{cargo}:{eleito}:{meios_contato}:{limit}"
    log.info(
        "eleitos_pedido",
        ano=ano, uf=uf, municipio=mun, cargo=cargo, eleito=eleito,
    )
    return cached_agg(
        chave,
        lambda: _calcular_eleitos(
            db, ano, uf, mun, cargo, eleito, meios_contato, limit,
        ),
    )


def _calcular_eleitos(
    db: Session, ano: int, uf: str, mun: str | None, cargo: int | None,
    eleito: bool, meios_contato: bool, limit: int,
) -> dict[str, Any]:
    filtro = _eh_eleito_sql() if eleito else ~_eh_eleito_sql()

    stmt = (
        select(
            Candidate.id, Candidate.name, Candidate.urn_name, Candidate.number,
            Candidate.office_name, Candidate.office_code,
            Candidate.result_status, Candidate.total_votes,
            Candidate.social_links, Party.abbreviation.label("partido"),
        )
        .select_from(Candidate)
        .join(Election, Election.id == Candidate.election_id)
        .join(Party, Party.id == Candidate.party_id)
        .where(Election.year == ano, Candidate.state == uf, filtro)
        .order_by(Candidate.total_votes.desc().nullslast())
        .limit(limit)
    )
    if cargo is not None:
        stmt = stmt.where(Candidate.office_code == cargo)

    municipio_nome = None
    if mun is not None:
        alvo = _achar_municipio(db, uf, mun)
        municipio_nome = alvo.name
        stmt = stmt.where(
            Candidate.id.in_(
                select(VoteResult.candidate_id)
                .where(VoteResult.municipality_id == alvo.id)
            )
        )

    itens: list[dict[str, Any]] = []
    for r in db.execute(stmt):
        item: dict[str, Any] = {
            "id": str(r.id),
            "nome": r.name,
            "nome_urna": r.urn_name,
            "numero": r.number,
            "partido": r.partido,
            "cargo": r.office_name,
            "cargo_codigo": r.office_code,
            "situacao": r.result_status,
            "votos": int(r.total_votes or 0),
            "municipio": municipio_nome,
        }
        if meios_contato:
            # So existe rede social, e apenas em parte das candidaturas: o TSE
            # nao publica telefone nem e-mail de candidato.
            item["redes_sociais"] = r.social_links or []
        itens.append(item)

    aviso = (
        "Sem filtro de turno: a situacao ja e o resultado final. 'Eleito' cobre "
        "ELEITO, ELEITO POR QP e ELEITO POR MEDIA — filtrar so por 'ELEITO' "
        "perderia quase todo vereador e deputado."
    )
    if meios_contato:
        aviso += (
            " Meios de contato: a fonte traz apenas redes sociais, e so em parte "
            "das candidaturas. Telefone e e-mail nao existem no dado do TSE."
        )

    log.info("eleitos_pronto", ano=ano, uf=uf, municipio=mun, linhas=len(itens))
    return {
        "ano": ano, "uf": uf, "municipio": municipio_nome,
        "eleito": eleito, "total": len(itens),
        "observacao": aviso, "itens": itens,
    }


# -------------------------------------------------------- perfil do eleitorado

def get_electorate_profile(
    db: Session, *, ano: int, uf: str, municipio: str | None = None,
) -> dict[str, Any]:
    """Perfil do eleitorado do recorte. Sem municipio, soma a UF inteira.

    Nao existe perfil por turno: o TSE publica um eleitorado por pleito.
    """
    uf = (uf or "").strip().upper()
    mun = (municipio or "").strip().upper() or None
    chave = f"eleitorado:{ano}:{uf}:{mun}"
    log.info("eleitorado_pedido", ano=ano, uf=uf, municipio=mun)
    return cached_agg(chave, lambda: _calcular_eleitorado(db, ano, uf, mun))


_DIMENSOES = {
    "sexo": "by_gender",
    "faixa_etaria": "by_age",
    "escolaridade": "by_education",
    "estado_civil": "by_marital_status",
    "cor_raca": "by_race",
}


def _calcular_eleitorado(
    db: Session, ano: int, uf: str, mun: str | None,
) -> dict[str, Any]:
    stmt = (
        select(MunicipalityElectorate)
        .join(
            Municipality,
            Municipality.id == MunicipalityElectorate.municipality_id,
        )
        .where(MunicipalityElectorate.year == ano, Municipality.state == uf)
    )

    municipio_nome = None
    if mun is not None:
        alvo = _achar_municipio(db, uf, mun)
        municipio_nome = alvo.name
        stmt = stmt.where(MunicipalityElectorate.municipality_id == alvo.id)

    linhas = list(db.execute(stmt).scalars())

    total = 0
    dims: dict[str, dict[str, int]] = {nome: {} for nome in _DIMENSOES}
    for linha in linhas:
        total += int(linha.total or 0)
        for destino, campo in _DIMENSOES.items():
            for chave, valor in (getattr(linha, campo) or {}).items():
                dims[destino][chave] = dims[destino].get(chave, 0) + int(valor or 0)

    aviso = "Nao existe perfil por turno: o TSE publica um eleitorado por pleito."
    if ano not in ANOS_COM_ELEITORADO:
        aviso += (
            f" O ano {ano} nao esta carregado — hoje temos "
            f"{', '.join(str(a) for a in ANOS_COM_ELEITORADO)}."
        )

    # A armadilha aqui nao e falta de dado, e dado que existe dizendo "nao sei".
    # Cor/raca e declaracao OPCIONAL: no RJ 2024, 12.039.902 dos 13.033.929
    # eleitores estao como "Nao informado" — 92%. A dimensao SOMA o total, entao
    # uma medida de cobertura simples nao acusaria nada, e quem dividisse Parda
    # (416.547) pelo total leria 3,2% quando o correto, entre quem declarou, e
    # 41,9%. Por isso devolvemos quanto de cada dimensao e "nao informado".
    def _e_nao_informado(chave: str) -> bool:
        c = _sem_acento(chave).upper()
        return "NAO INFORMAD" in c or "NAO DIVULGA" in c or c in ("#NULO#", "#NE#")

    nao_informado = {
        nome: (
            round(
                sum(v for k, v in valores.items() if _e_nao_informado(k))
                / sum(valores.values()),
                4,
            )
            if sum(valores.values())
            else 0.0
        )
        for nome, valores in dims.items()
    }
    vagas = [n for n, frac in nao_informado.items() if frac >= 0.20]
    if vagas:
        aviso += (
            " Atencao: em " + ", ".join(vagas) + " boa parte do eleitorado esta "
            "como 'Nao informado' (e declaracao opcional no TSE). Para percentual, "
            "use como denominador o total MENOS os nao informados — ver o campo "
            "`nao_informado`."
        )

    log.info(
        "eleitorado_pronto",
        ano=ano, uf=uf, municipios=len(linhas), total=total,
        vagas=",".join(vagas) or None,
    )
    return {
        "ano": ano, "uf": uf, "municipio": municipio_nome,
        "municipios_somados": len(linhas), "total_eleitores": total,
        "nao_informado": nao_informado, "observacao": aviso, **dims,
    }


__all__ = ["get_elected", "get_electorate_profile"]
