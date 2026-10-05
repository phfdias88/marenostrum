"""Epocas de partido NO BANCO: cria as linhas e reponta as candidaturas antigas.

`tse_parties` nasceu com uma linha por numero, com o nome de HOJE. O candidato
do DEM de 2016 apontava para a linha "PRD", o do PSC de 2022 para "PODE", e
toda tela de ano antigo mostrava a sigla errada. Aqui cada candidatura passa a
apontar para a linha da EPOCA dela (`app.utils.partidos.EPOCAS`).

TRES REGRAS que nao podem ser quebradas — cada uma ja custou um defeito:

  * A LINHA QUE EXISTE HOJE CONTINUA SENDO A EPOCA ATUAL, com o mesmo id. A
    filiacao partidaria aponta para ela (retrato de hoje) e os candidatos da
    eleicao em apuracao tambem. As epocas passadas sao linhas NOVAS, e quem
    muda de linha sao as candidaturas antigas. Nunca se apaga linha de partido
    fora do `desfazer`: a filiacao iria junto, em cascata e em silencio.
  * TODA EPOCA TEM DATA, MENOS A MAIS ANTIGA. `partido_atual` devolve a linha
    de maior `valid_from`; se a linha de hoje ficasse sem data, o cartao do 25
    passaria a dizer "DEM".
  * UMA LINHA POR (NUMERO, ANO). Quem decide a epoca e o ano da eleicao. Se o
    mesmo numero ficasse em duas linhas no mesmo ano, o desempenho por partido
    (que agrupa por linha) mostraria duas barras para um partido so.

O que NAO muda: o NUMERO do partido de nenhuma candidatura. Por isso a prova de
que nada se perdeu e simples — o retrato (ano, numero) -> (candidaturas, votos,
eleitos) tem de sair identico antes e depois.

Roda em fatias pequenas, com commit entre elas: sao ~280 mil linhas numa tabela
com quinze indices, num servidor de 1 vCPU que esta atendendo gente.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID, uuid4

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.tse.candidate import Candidate
from app.models.tse.election import Election
from app.models.tse.party import Party
from app.models.tse.party_membership import PartyMembership
from app.utils.partidos import EPOCAS, normalizar_sigla, partido_atual

log = structlog.get_logger("marenostrum.services.epocas_de_partido")


@dataclass(frozen=True)
class Movimento:
    """Um grupo de candidaturas que esta na linha errada para o ano delas."""
    numero: int
    ano: int
    origem: UUID
    destino: UUID
    sigla_origem: str
    sigla_destino: str
    quantidade: int


def _linhas_por_numero(db: Session) -> dict[int, list[Party]]:
    por_numero: dict[int, list[Party]] = {}
    for p in db.execute(select(Party)).scalars():
        por_numero.setdefault(p.number, []).append(p)
    return por_numero


def _linha_do_ano(linhas: list[Party], ano: int) -> Party:
    """A linha que valia naquele ano — mesma regra de IndiceDePartidos._vigente."""
    ate_o_ano = [l for l in linhas if (l.valid_from or 0) <= ano]
    if ate_o_ano:
        return max(ate_o_ano, key=lambda l: l.valid_from or 0)
    # Ano anterior a todas as linhas: a mais antiga e o melhor palpite.
    return min(linhas, key=lambda l: l.valid_from or 0)


# --------------------------------------------------------------- as linhas

def garantir_epocas(db: Session) -> dict[str, Any]:
    """Data a linha de hoje e cria as linhas das epocas passadas. Idempotente.

    Devolve o que fez (para o manifesto do `desfazer`) e o que deixou de fazer
    — numero cuja linha de hoje nao e a que a tabela de epocas espera fica
    INTOCADO e e listado: mexer nele seria chutar.
    """
    criadas: list[dict[str, Any]] = []
    datadas: list[dict[str, Any]] = []
    ignorados: list[str] = []

    por_numero = _linhas_por_numero(db)
    for numero, epocas in sorted(EPOCAS.items()):
        linhas = por_numero.get(numero)
        if not linhas:
            continue                                   # o banco nem tem esse numero
        atual = partido_atual(linhas)
        if normalizar_sigla(atual.abbreviation) != normalizar_sigla(epocas.sigla_atual):
            ignorados.append(
                f"{numero}: a linha de hoje e '{atual.abbreviation}', a tabela "
                f"de epocas espera '{epocas.sigla_atual}'"
            )
            continue

        # PRIMEIRO a data da linha de hoje. A epoca antiga do 22 tambem se chama
        # "PL" e tambem nao tem data: criada antes, colidiria com a atual no
        # indice unico (number, abbreviation, coalesce(valid_from, 0)).
        if atual.valid_from is None:
            datadas.append({"id": str(atual.id), "numero": numero,
                            "sigla": atual.abbreviation, "antes": None,
                            "depois": epocas.desde_atual})
            atual.valid_from = epocas.desde_atual
            db.flush()
        elif atual.valid_from != epocas.desde_atual:
            ignorados.append(
                f"{numero}: a linha '{atual.abbreviation}' ja tem data "
                f"{atual.valid_from} (a tabela diz {epocas.desde_atual}); mantida"
            )

        for e in epocas.passadas:
            ja_existe = any(
                l is not atual
                and normalizar_sigla(l.abbreviation) == normalizar_sigla(e.sigla)
                and (l.valid_from or 0) == (e.desde or 0)
                for l in linhas
            )
            if ja_existe:
                continue
            nova = Party(id=uuid4(), number=numero, abbreviation=e.sigla,
                         name=e.nome, valid_from=e.desde)
            db.add(nova)
            linhas.append(nova)
            criadas.append({"id": str(nova.id), "numero": numero, "sigla": e.sigla,
                            "desde": e.desde, "linha_atual": str(atual.id)})
    db.flush()
    log.info("epocas_garantidas", criadas=len(criadas), datadas=len(datadas),
             ignorados=len(ignorados))
    return {"criadas": criadas, "datadas": datadas, "ignorados": ignorados}


# ----------------------------------------------------------------- o plano

def planejar(db: Session) -> list[Movimento]:
    """Grupos (linha, ano) de candidaturas que nao estao na linha da sua epoca.

    So olha os numeros da tabela de epocas. Recalculado a cada chamada: rodar
    de novo depois de uma interrupcao continua de onde parou.
    """
    por_numero = _linhas_por_numero(db)
    movimentos: list[Movimento] = []
    for numero in sorted(EPOCAS):
        linhas = por_numero.get(numero)
        if not linhas or len(linhas) < 2:
            continue
        por_id = {l.id: l for l in linhas}
        contagem = db.execute(
            select(Candidate.party_id, Election.year, func.count(Candidate.id))
            .join(Election, Election.id == Candidate.election_id)
            .where(Candidate.party_id.in_(list(por_id)))
            .group_by(Candidate.party_id, Election.year)
        ).all()
        for party_id, ano, quantidade in contagem:
            destino = _linha_do_ano(linhas, ano)
            if destino.id != party_id:
                movimentos.append(Movimento(
                    numero=numero, ano=ano, origem=party_id, destino=destino.id,
                    sigla_origem=por_id[party_id].abbreviation,
                    sigla_destino=destino.abbreviation, quantidade=int(quantidade),
                ))
    return sorted(movimentos, key=lambda m: (m.numero, m.ano))


# --------------------------------------------------------------- o reponte

def _mover(
    db: Session, *, origem: UUID, destino: UUID, ano: int | None, fatia: int,
    pausa: Callable[[float], None] | None,
) -> int:
    """Troca party_id de `origem` para `destino`, em fatias com commit.

    A fatia entra por id (subconsulta com LIMIT): o UPDATE nunca passa de
    `fatia` linhas, entao nenhuma transacao segura lock nem WAL por muito
    tempo. A guarda `party_id == origem` torna cada fatia repetivel.
    """
    total = 0
    while True:
        inicio = time.monotonic()
        alvo = select(Candidate.id).where(Candidate.party_id == origem)
        if ano is not None:
            alvo = alvo.where(Candidate.election_id.in_(
                select(Election.id).where(Election.year == ano)
            ))
        feitas = db.execute(
            update(Candidate)
            .where(Candidate.id.in_(alvo.limit(fatia)))
            .values(party_id=destino)
            .execution_options(synchronize_session=False)
        ).rowcount
        db.commit()
        if not feitas:
            return total
        total += feitas
        if pausa is not None:
            pausa(time.monotonic() - inicio)


def repontar(
    db: Session, movimento: Movimento, *, fatia: int = 4000,
    pausa: Callable[[float], None] | None = None,
) -> int:
    """Leva o grupo para a linha da epoca. Devolve quantas linhas mudou."""
    feitas = _mover(db, origem=movimento.origem, destino=movimento.destino,
                    ano=movimento.ano, fatia=fatia, pausa=pausa)
    log.info("epoca_repontada", numero=movimento.numero, ano=movimento.ano,
             de=movimento.sigla_origem, para=movimento.sigla_destino, linhas=feitas)
    return feitas


# -------------------------------------------------------------- a conferencia

@dataclass(frozen=True)
class LinhaDoRetrato:
    ano: int
    numero: int
    party_id: UUID
    sigla: str
    candidaturas: int
    votos: int
    eleitos: int


def retrato(db: Session) -> list[LinhaDoRetrato]:
    """Candidaturas, votos e eleitos por (ano, numero, LINHA de partido).

    Uma leitura so da tabela inteira; serve para as duas provas: somado por
    (ano, numero) tem de ser identico antes e depois, e nenhum (ano, numero)
    pode ficar em duas linhas.
    """
    linhas = db.execute(
        select(
            Election.year, Party.number, Party.id, Party.abbreviation,
            func.count(Candidate.id),
            func.coalesce(func.sum(Candidate.total_votes), 0),
            func.count(Candidate.id).filter(Candidate.result_status.like("ELEITO%")),
        )
        .select_from(Candidate)
        .join(Election, Election.id == Candidate.election_id)
        .join(Party, Party.id == Candidate.party_id)
        .group_by(Election.year, Party.number, Party.id, Party.abbreviation)
    ).all()
    return [
        LinhaDoRetrato(ano, numero, pid, sigla, int(n), int(votos), int(eleitos))
        for ano, numero, pid, sigla, n, votos, eleitos in linhas
    ]


def por_ano_e_numero(foto: list[LinhaDoRetrato]) -> dict[tuple[int, int], tuple[int, int, int]]:
    """O retrato sem a linha: e isto que nao pode mudar com o reponte."""
    saida: dict[tuple[int, int], tuple[int, int, int]] = {}
    for l in foto:
        a, b, c = saida.get((l.ano, l.numero), (0, 0, 0))
        saida[(l.ano, l.numero)] = (a + l.candidaturas, b + l.votos, c + l.eleitos)
    return saida


def anos_divididos(foto: list[LinhaDoRetrato]) -> dict[tuple[int, int], list[str]]:
    """(ano, numero) cujas candidaturas estao em mais de uma linha de partido."""
    linhas: dict[tuple[int, int], dict[UUID, str]] = {}
    for l in foto:
        linhas.setdefault((l.ano, l.numero), {})[l.party_id] = l.sigla
    return {k: sorted(v.values()) for k, v in linhas.items() if len(v) > 1}


def conferir(db: Session) -> list[str]:
    """Problemas de estrutura nas linhas de partido. Lista vazia = tudo certo.

    Barato (so tse_parties e a filiacao agregada): da para rodar a qualquer hora.
    """
    problemas: list[str] = []
    por_numero = _linhas_por_numero(db)
    for numero, linhas in sorted(por_numero.items()):
        sem_data = [l.abbreviation for l in linhas if l.valid_from is None]
        if len(sem_data) > 1:
            problemas.append(f"{numero}: {len(sem_data)} linhas sem data {sem_data} — "
                             "qual e a de hoje depende da ordem do banco")
        datas = [l.valid_from or 0 for l in linhas]
        if len(set(datas)) != len(datas):
            problemas.append(f"{numero}: duas linhas com a mesma data {sorted(datas)}")
        epocas = EPOCAS.get(numero)
        if epocas and len(linhas) > 1:
            atual = partido_atual(linhas)
            if normalizar_sigla(atual.abbreviation) != normalizar_sigla(epocas.sigla_atual):
                problemas.append(
                    f"{numero}: a linha de hoje saiu '{atual.abbreviation}', "
                    f"deveria ser '{epocas.sigla_atual}'"
                )

    # Filiacao e retrato de HOJE: tem de estar toda na linha atual do numero.
    atuais = {partido_atual(linhas).id for linhas in por_numero.values()}
    fora = db.execute(
        select(Party.number, Party.abbreviation, func.count())
        .select_from(PartyMembership)
        .join(Party, Party.id == PartyMembership.party_id)
        .where(PartyMembership.party_id.notin_(list(atuais)))
        .group_by(Party.number, Party.abbreviation)
    ).all()
    for numero, sigla, n in fora:
        problemas.append(f"{numero}: {n} linhas de filiacao presas a epoca antiga '{sigla}'")
    return problemas


# ------------------------------------------------------------------ desfazer

def desfazer(
    db: Session, manifesto: dict[str, Any], *, fatia: int = 4000,
    pausa: Callable[[float], None] | None = None,
) -> dict[str, int]:
    """Volta ao estado anterior ao manifesto: uma linha por numero.

    Devolve as candidaturas das linhas criadas para a linha atual, apaga SO as
    linhas que o manifesto diz ter criado e tira a data que ele diz ter posto.
    """
    devolvidas = 0
    for c in manifesto.get("criadas", []):
        devolvidas += _mover(db, origem=UUID(c["id"]), destino=UUID(c["linha_atual"]),
                             ano=None, fatia=fatia, pausa=pausa)
    apagadas = 0
    for c in manifesto.get("criadas", []):
        apagadas += db.execute(delete(Party).where(Party.id == UUID(c["id"]))).rowcount
    db.flush()
    for d in manifesto.get("datadas", []):
        db.execute(update(Party).where(Party.id == UUID(d["id"]))
                   .values(valid_from=d["antes"]))
    db.commit()
    log.info("epocas_desfeitas", candidaturas=devolvidas, linhas_apagadas=apagadas)
    return {"candidaturas_devolvidas": devolvidas, "linhas_apagadas": apagadas,
            "datas_retiradas": len(manifesto.get("datadas", []))}
