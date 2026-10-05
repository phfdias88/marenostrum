"""Captura dos resultados AO VIVO do TSE, na noite da apuracao.

POR QUE EXISTE UM SEGUNDO CAMINHO. O TSE publica resultado por dois canais, e
eles respondem em tempos muito diferentes:

  consolidado  cdn.tse.jus.br/.../votacao_candidato_munzona_<ano>.zip
               E o que o resto do sistema consome. No dia da eleicao ele existe
               mas vem VAZIO — em 04/10/2026 eram 29 CSVs com zero linhas e um
               leiame.pdf. Historicamente so e preenchido dias depois.

  ao vivo      resultados.tse.jus.br/oficial/ele<ano>/<eleicao>/dados/...
               JSON por municipio e por UF, atualizado durante a apuracao. E a
               fonte da propria pagina de resultados do TSE.

"Assim que os dados forem disponibilizados" significa o segundo. Este modulo le
de la e grava nas MESMAS tabelas que o importador consolidado usa, de forma que
quando o zip oficial sair ele substitui tudo sem duplicar:

  - candidato casa por `sq_candidato`, que o feed traz como `sqcand`. O
    importador consolidado reaproveita quem ja existe.
  - o importador consolidado APAGA os VoteResult do ano antes de regravar.
    O que entrou por aqui e descartado e trocado pelo numero oficial.

TRES REGRAS QUE NAO SE NEGOCIAM, cada uma veio de um erro ja cometido aqui:

  1. Upsert de SUBSTITUICAO, nunca de soma. A captura roda varias vezes na
     noite e o feed entrega o acumulado, nao o incremento. Somar dobraria.
  2. Turno no lugar certo: 1o turno em tse_vote_results, 2o em
     tse_runoff_votes. Misturar faria um candidato aparecer com os dois
     turnos somados.
  3. Nada de sucesso silencioso. Cada arquivo que falha e contado e devolvido;
     "capturou" sem dizer quanto faltou e o pior tipo de resultado.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID, uuid4

import httpx
import structlog
from contextlib import contextmanager

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.tse.candidate import Candidate
from app.models.tse.election import Election
from app.models.tse.municipality import Municipality
from app.models.tse.party import Party
from app.models.tse.runoff_vote import TseRunoffVote
from app.models.tse.vote_result import VoteResult
from app.utils.partidos import IndiceDePartidos

log = structlog.get_logger("marenostrum.services.tse_live")

BASE = "https://resultados.tse.jus.br/oficial"
CABECALHOS = {"User-Agent": "Mozilla/5.0 (MareNostrum; captura de resultados)"}

# So cargo que RECEBE voto. O registro de candidaturas tambem lista vice (2, 4)
# e suplente de senador (9, 10), que nao aparecem no resultado: criar essas
# linhas poluiria a busca com candidatura que nunca tera votacao.
CARGOS_COM_VOTO = (1, 3, 5, 6, 7, 8)

CHUNK = 5000


def _i(v: Any) -> int:
    """Inteiro tolerante: o feed manda numero como texto, as vezes com ponto."""
    if v is None:
        return 0
    try:
        return int(str(v).strip().replace(".", "") or 0)
    except ValueError:
        return 0


def _situacao_limpa(v: Any) -> str | None:
    t = (str(v or "")).strip()
    return None if (not t or t.startswith("#")) else t[:40]


def _pct(v: Any) -> float:
    """Percentual com virgula decimal, como o TSE escreve ('87,34')."""
    try:
        return float(str(v or "0").strip().replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


# ------------------------------------------------- candidatos pelo registro

def importar_candidatos_do_registro(
    db: Session, zip_path: Path, *, ano: int,
) -> dict[str, int]:
    """Cria Election/Party/Candidate do ano a partir do consulta_cand.

    Sem isto nao ha onde pendurar o voto que chega pelo feed: quem cria
    candidato no fluxo normal e o arquivo de RESULTADO, que na noite da eleicao
    ainda esta vazio.

    As colunas e a logica espelham _process_candidato_munzona de proposito —
    quando o consolidado rodar, ele acha estes mesmos candidatos por
    `sq_candidato` e segue sem duplicar. Idempotente: quem ja existe e pulado.
    """
    eleicoes = {e.tse_code: e.id for e in db.execute(select(Election)).scalars()}
    partidos = IndiceDePartidos.do_banco(db)
    ja_existe = set(
        db.execute(
            select(Candidate.sq_candidato)
            .join(Election, Election.id == Candidate.election_id)
            .where(Election.year == ano)
        ).scalars()
    )

    agora = datetime.now(timezone.utc)
    novas_eleicoes: list[dict] = []
    novos_partidos: list[dict] = []
    novos_candidatos: list[dict] = []
    lidos = pulados_cargo = 0

    with zipfile.ZipFile(zip_path) as z:
        nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
        # O zip traz um CSV por UF mais o _BRASIL com os mesmos dados — ler os
        # dois dobraria tudo.
        nacionais = [n for n in nomes if "_brasil" in n.lower()]
        for nome in (nacionais or nomes):
            with z.open(nome) as f:
                leitor = csv.DictReader(
                    io.TextIOWrapper(f, encoding="latin-1"), delimiter=";",
                )
                for row in leitor:
                    lidos += 1
                    cargo = _i(row.get("CD_CARGO"))
                    if cargo not in CARGOS_COM_VOTO:
                        pulados_cargo += 1
                        continue
                    sq = _i(row.get("SQ_CANDIDATO"))
                    cod_eleicao = _i(row.get("CD_ELEICAO"))
                    num_partido = _i(row.get("NR_PARTIDO"))
                    if not sq or not cod_eleicao or not num_partido:
                        continue

                    if cod_eleicao not in eleicoes:
                        eid = uuid4()
                        eleicoes[cod_eleicao] = eid
                        novas_eleicoes.append({
                            "id": eid, "tse_code": cod_eleicao,
                            "year": _i(row.get("ANO_ELEICAO")) or ano,
                            "round": _i(row.get("NR_TURNO")) or 1,
                            "name": (row.get("DS_ELEICAO") or "")[:180],
                            "type_name": (row.get("NM_TIPO_ELEICAO") or "")[:80],
                            "created_at": agora, "updated_at": agora,
                        })
                    sigla = (row.get("SG_PARTIDO") or "").strip()[:20]
                    pid = (
                        partidos.achar_exato(num_partido, sigla) if sigla
                        else partidos.achar(num_partido, None, ano)
                    )
                    if pid is None:
                        # Sigla que este numero nunca teve: ou o numero foi
                        # dado a outro partido (14: PTB -> MISSAO), ou o mesmo
                        # partido mudou de nome (35: PMB -> DEMOCRATA). Este e
                        # o registro da eleicao mais recente, entao abre uma
                        # epoca nova em vez de herdar a sigla antiga — foi
                        # assim que o candidato do Missao saiu como "PTB".
                        pid = uuid4()
                        desde = ano if partidos.conhece(num_partido) else None
                        partidos.registrar(num_partido, sigla, pid, desde)
                        novos_partidos.append({
                            "id": pid, "number": num_partido,
                            "abbreviation": sigla,
                            "name": (row.get("NM_PARTIDO") or "")[:180],
                            "valid_from": desde,
                            "created_at": agora, "updated_at": agora,
                        })
                    if sq in ja_existe:
                        continue
                    ja_existe.add(sq)
                    novos_candidatos.append({
                        "id": uuid4(), "sq_candidato": sq,
                        "election_id": eleicoes[cod_eleicao],
                        "number": _i(row.get("NR_CANDIDATO")),
                        "name": (row.get("NM_CANDIDATO") or "")[:180],
                        "urn_name": (row.get("NM_URNA_CANDIDATO") or "")[:180],
                        "party_id": pid,
                        "office_code": cargo,
                        "office_name": (row.get("DS_CARGO") or "")[:40],
                        "state": (row.get("SG_UF") or "")[:2].upper(),
                        # O registro traz '#NE' (nao informado) nesta coluna no
                        # dia da eleicao, e o importador consolidado NUNCA
                        # atualiza candidato que ja existe — o lixo ficaria
                        # gravado para sempre. Melhor vazio.
                        "situation": _situacao_limpa(row.get("DS_SITUACAO_CANDIDATURA")),
                        # Sem resultado ainda: o feed preenche durante a apuracao.
                        "result_status": None,
                        "created_at": agora, "updated_at": agora,
                    })

    from sqlalchemy import insert

    if novas_eleicoes:
        db.execute(insert(Election), novas_eleicoes)
    if novos_partidos:
        db.execute(insert(Party), novos_partidos)
    for i in range(0, len(novos_candidatos), CHUNK):
        db.execute(insert(Candidate), novos_candidatos[i : i + CHUNK])
    db.commit()

    resumo = {
        "lidos": lidos,
        "ignorados_vice_e_suplente": pulados_cargo,
        "eleicoes_criadas": len(novas_eleicoes),
        "partidos_criados": len(novos_partidos),
        "candidatos_criados": len(novos_candidatos),
    }
    log.info("tse_live_registro_importado", ano=ano, **resumo)
    return resumo


# ------------------------------------------------------------ leitura do feed

def url_do_arquivo(
    ano: int, eleicao: int, uf: str, cargo: int, municipio: int | None = None,
) -> str:
    """URL do arquivo de resultado. Sem municipio = nivel UF (ou BR)."""
    uf = uf.lower()
    area = f"{uf}{municipio:05d}" if municipio else uf
    return (
        f"{BASE}/ele{ano}/{eleicao}/dados/{uf}/"
        f"{area}-c{cargo:04d}-e{eleicao:06d}-u.json"
    )


def extrair_candidatos(dado: dict) -> list[dict[str, Any]]:
    """Achata carg -> agr -> par -> cand numa lista simples.

    O mesmo candidato nunca aparece em dois ramos: cada um pertence a um
    partido, que pertence a uma agremiacao. Mesmo assim deduplicamos por
    `sqcand` — se o TSE mudar o aninhamento, preferimos contar de menos a contar
    em dobro.
    """
    vistos: dict[int, dict[str, Any]] = {}
    for cargo in dado.get("carg") or []:
        for agr in cargo.get("agr") or []:
            for par in agr.get("par") or []:
                for c in par.get("cand") or []:
                    sq = _i(c.get("sqcand"))
                    if not sq or sq in vistos:
                        continue
                    vistos[sq] = {
                        "sqcand": sq,
                        "votos": _i(c.get("vap")),
                        "situacao": (c.get("st") or "").strip() or None,
                        "eleito": (c.get("e") or "").strip().lower() == "s",
                    }
    return list(vistos.values())


def andamento(dado: dict) -> dict[str, Any]:
    """Quanto da apuracao daquela area ja foi totalizado."""
    s = dado.get("s") or {}
    e = dado.get("e") or {}
    return {
        "turno": _i(dado.get("t")) or 1,
        "secoes_total": _i(s.get("ts")),
        "secoes_totalizadas": _i(s.get("st")),
        "pct_secoes": _pct(s.get("pst")),
        "eleitorado": _i(e.get("te")),
        "comparecimento": _i(e.get("c")),
        "gerado_em": f"{dado.get('dg', '')} {dado.get('hg', '')}".strip(),
    }


def baixar(cliente: httpx.Client, url: str) -> dict | None:
    """JSON do feed, ou None se nao der. 404 e normal: area ainda sem arquivo."""
    try:
        r = cliente.get(url)
    except httpx.HTTPError as exc:
        log.warning("tse_live_rede", url=url, erro=str(exc)[:120])
        return None
    if r.status_code != 200:
        if r.status_code != 404:
            log.warning("tse_live_http", url=url, status=r.status_code)
        return None
    try:
        return r.json()
    except ValueError:
        log.warning("tse_live_json_invalido", url=url, bytes=len(r.content))
        return None


# ------------------------------------------------------------------ gravacao

def _insert_do_dialeto(db: Session):
    """`INSERT ... ON CONFLICT` existe no Postgres e no SQLite, mas cada um tem
    a sua construcao no SQLAlchemy. Escolher aqui deixa a regra de substituicao
    coberta pela suite (que roda em SQLite) em vez de so valer em producao."""
    nome = getattr(getattr(db.bind, "dialect", None), "name", "")
    return sqlite_insert if nome == "sqlite" else pg_insert


def gravar_votos_do_municipio(
    db: Session,
    *,
    candidatos_por_sq: dict[int, UUID],
    municipio_id: UUID,
    turno: int,
    candidatos: Iterable[dict[str, Any]],
) -> tuple[int, int]:
    """Grava os votos de um municipio. Devolve (gravados, sem_candidato).

    SUBSTITUI, nao soma: o feed entrega o acumulado e a captura se repete a
    noite toda. `sem_candidato` conta quem veio no feed mas nao esta no nosso
    registro — nao deveria acontecer, e se acontecer tem de aparecer.
    """
    tabela = TseRunoffVote if turno == 2 else VoteResult
    agora = datetime.now(timezone.utc)
    linhas, perdidos = [], 0
    for c in candidatos:
        cid = candidatos_por_sq.get(c["sqcand"])
        if cid is None:
            perdidos += 1
            continue
        linhas.append({
            "id": uuid4(), "candidate_id": cid, "municipality_id": municipio_id,
            "votes": c["votos"], "created_at": agora, "updated_at": agora,
        })

    insert_ = _insert_do_dialeto(db)
    for i in range(0, len(linhas), CHUNK):
        bloco = linhas[i : i + CHUNK]
        stmt = insert_(tabela.__table__).values(bloco)
        stmt = stmt.on_conflict_do_update(
            index_elements=["candidate_id", "municipality_id"],
            set_={"votes": stmt.excluded.votes, "updated_at": agora},
        )
        db.execute(stmt)
    return len(linhas), perdidos


def gravar_totais_do_candidato(
    db: Session,
    *,
    candidatos_por_sq: dict[int, UUID],
    turno: int,
    candidatos: Iterable[dict[str, Any]],
) -> int:
    """Total e situacao do candidato, a partir do arquivo de nivel UF (ou BR).

    So no 1o turno: `total_votes` significa votacao de 1o turno no resto do
    sistema, e sobrescrever com o 2o esconderia o numero que todas as telas
    exibem. A situacao (ELEITO / NAO ELEITO) vale nos dois.

    Em lote por chave primaria: o ensaio da noite do 1o turno levou 144s para
    18.853 candidatos fazendo um UPDATE por vez, num servidor de 1 vCPU que
    repete isso a noite inteira.
    """
    com_total: list[dict[str, Any]] = []
    so_situacao: list[dict[str, Any]] = []
    so_total: list[dict[str, Any]] = []

    for c in candidatos:
        cid = candidatos_por_sq.get(c["sqcand"])
        if cid is None:
            continue
        situacao = c["situacao"].upper()[:40] if c["situacao"] else None
        if turno == 1 and situacao:
            com_total.append(
                {"id": cid, "total_votes": c["votos"], "result_status": situacao})
        elif turno == 1:
            so_total.append({"id": cid, "total_votes": c["votos"]})
        elif situacao:
            so_situacao.append({"id": cid, "result_status": situacao})

    # Um executemany por FORMATO de linha: o bulk-update por PK do SQLAlchemy
    # exige que todos os dicionarios do lote tenham as mesmas chaves.
    for lote in (com_total, so_total, so_situacao):
        if lote:
            db.execute(update(Candidate), lote)
    return len(com_total) + len(so_total) + len(so_situacao)


# ------------------------------------- convivencia com a carga consolidada
#
# O importador consolidado apaga os votos do ano, da commit, e so depois grava
# — somando, em flushes parciais. Se uma passada ao vivo escrever nesse meio, a
# soma cai por cima do que ela gravou e o voto sai EM DOBRO, em silencio. As
# duas guardas abaixo existem para que os dois caminhos nunca escrevam juntos.

def _chave_da_trava(ano: int) -> int:
    return 7_400_000 + ano


@contextmanager
def trava_do_ano(ano: int, *, esperar: bool):
    """Exclusao mutua entre a captura ao vivo e a carga consolidada do ano.

    Trava consultiva do Postgres, em conexao DEDICADA: a sessao normal devolve a
    conexao ao pool a cada commit, e a trava ficaria presa numa conexao que
    ninguem mais segura. Por isso tambem o desbloqueio explicito no fim.

    `esperar=False` (captura ao vivo): se a carga consolidada esta rodando, esta
    passada desiste — havera outra em minutos. `esperar=True` (consolidada):
    aguarda a passada ao vivo terminar; ela e curta.
    """
    from app.core.database import engine

    if engine.dialect.name != "postgresql":
        yield True
        return

    chave = _chave_da_trava(ano)
    conn = engine.connect()
    pegou = False
    try:
        if esperar:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": chave})
            pegou = True
        else:
            pegou = bool(conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": chave}).scalar())
        yield pegou
    finally:
        if pegou:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": chave})
        conn.close()


def consolidado_ja_entrou(db: Session, ano: int) -> str | None:
    """A carga OFICIAL do ano ja rodou, ou esta rodando? Devolve o motivo.

    Depois que o numero oficial entra, a captura ao vivo nao tem mais nada a
    fazer no 1o turno — e escrever por cima trocaria dado consolidado por dado
    de divulgacao. Enquanto o job esta em andamento, escrever junto dobra voto.
    """
    from app.models.tse.sync_job import SyncJobStatus, TseSyncJob

    jobs = db.execute(
        select(TseSyncJob).where(TseSyncJob.dataset == f"candidato_munzona_{ano}")
    ).scalars().all()
    for j in jobs:
        if j.status in (SyncJobStatus.PENDING, SyncJobStatus.RUNNING):
            return f"a carga consolidada de {ano} esta em andamento (job {j.id})"
        if j.status == SyncJobStatus.COMPLETED and (j.vote_results_imported or 0) > 0:
            return (f"a carga consolidada de {ano} ja gravou "
                    f"{j.vote_results_imported} linhas de voto oficiais")
    return None


def mapa_de_candidatos(db: Session, ano: int) -> dict[int, UUID]:
    return {
        sq: cid
        for sq, cid in db.execute(
            select(Candidate.sq_candidato, Candidate.id)
            .join(Election, Election.id == Candidate.election_id)
            .where(Election.year == ano)
        ).all()
    }


def mapa_de_municipios(db: Session, uf: str) -> dict[int, UUID]:
    return {
        cod: mid
        for cod, mid in db.execute(
            select(Municipality.tse_code, Municipality.id)
            .where(Municipality.state == uf.upper())
        ).all()
    }


__all__ = [
    "importar_candidatos_do_registro", "url_do_arquivo", "extrair_candidatos",
    "andamento", "baixar", "gravar_votos_do_municipio",
    "gravar_totais_do_candidato", "mapa_de_candidatos", "mapa_de_municipios",
    "CARGOS_COM_VOTO", "trava_do_ano", "consolidado_ja_entrou",
]
