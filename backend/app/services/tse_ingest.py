"""Guarda-corpos da ingestao do TSE, pensados para a apuracao de outubro/2026.

O socio pediu tolerancia a dado parcial e a mudanca de estrutura. A licao que
este projeto ja pagou e mais especifica que isso: **o perigo nao e falhar, e
ter sucesso pela metade em silencio**.

Ja aconteceu tres vezes aqui:
  - o ETL do censo gravou milhares de linhas TODAS NULAS porque o IBGE mudou a
    caixa de uma variavel (V0001 virou v0001) e ninguem percebeu;
  - um laco que deveria carregar 22 UFs nao carregou nenhuma, e o log dizia que
    tinha dado certo;
  - o aquecimento de cache respondia 401 em 283 de 295 chamadas gravando
    "warmup_ok".

Por isso este modulo tem duas funcoes, e so duas:

  validar_estrutura()  — confere as colunas ANTES de processar. Se o TSE mudar
                         o layout, o job MORRE dizendo qual coluna sumiu, em vez
                         de importar nulo e parecer bem-sucedido.

  cobertura()          — responde "o que ja entrou e o que falta", por UF. O TSE
                         libera a capital antes da cidade pequena; sem isto,
                         "importou" e indistinguivel de "importou metade".
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.tse.candidate import Candidate
from app.models.tse.election import Election
from app.models.tse.municipality import Municipality
from app.models.tse.vote_result import VoteResult

log = structlog.get_logger("marenostrum.services.tse_ingest")


class EstruturaInesperadaError(DomainError):
    """O arquivo do TSE nao tem as colunas que o processador espera.

    422 e nao 500: nao e defeito nosso, e contrato quebrado na origem. A
    mensagem diz exatamente o que falta, para a correcao ser de minutos.
    """

    status_code = 422
    code = "tse_estrutura_inesperada"


# Colunas SEM AS QUAIS o processador nao tem como fazer o trabalho. Nao e a
# lista completa do arquivo — e o minimo indispensavel. Coluna a mais no CSV
# nao atrapalha; coluna a menos, sim.
COLUNAS_MINIMAS: dict[str, tuple[str, ...]] = {
    "candidato_munzona": (
        "SQ_CANDIDATO", "CD_MUNICIPIO", "NR_TURNO", "QT_VOTOS_NOMINAIS",
        "NM_CANDIDATO", "NR_CANDIDATO", "SG_UF", "CD_CARGO", "NR_PARTIDO",
        "ANO_ELEICAO", "DS_SIT_TOT_TURNO",
    ),
    "votacao_secao": (
        "SQ_CANDIDATO", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO",
        "QT_VOTOS", "NR_TURNO",
    ),
    "locais_votacao": (
        "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO",
        "NM_BAIRRO", "QT_ELEITOR_SECAO", "SG_UF",
    ),
    "perfil_eleitorado": (
        "CD_MUNICIPIO", "DS_GENERO", "DS_FAIXA_ETARIA", "DS_GRAU_ESCOLARIDADE",
        "QT_ELEITORES_PERFIL",
    ),
}


# O TSE as vezes manda o CSV com marca de ordem de bytes. Lendo em latin-1 (que
# e o encoding dos arquivos deles) o BOM do UTF-8 nao vira "﻿": os tres
# bytes EF BB BF viram "ï»¿". Sem limpar as DUAS formas, a primeira coluna do
# arquivo fica com lixo grudado e a validacao acusa falta de uma coluna que
# existe — derrubando a importacao por um motivo inventado.
_MARCAS_DE_BOM = ("﻿", "ï»¿")


def ler_cabecalho(zip_path: Path) -> list[str]:
    """So o cabecalho. Nao abre o arquivo inteiro — o de SP tem 2,5 GB."""
    z = zipfile.ZipFile(zip_path)
    nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    with z.open(nome) as f:
        leitor = csv.reader(
            io.TextIOWrapper(f, encoding="latin-1"), delimiter=";"
        )
        colunas = []
        for c in next(leitor):
            c = c.strip()
            for marca in _MARCAS_DE_BOM:
                if c.startswith(marca):
                    c = c[len(marca):]
            colunas.append(c.strip())
        return colunas


def validar_estrutura(zip_path: Path, processador: str) -> dict[str, Any]:
    """Confere o cabecalho contra o minimo que o processador precisa.

    Levanta EstruturaInesperadaError se faltar coluna. Deixa passar colunas
    novas: o TSE acrescenta campo com frequencia e isso nunca quebrou nada.
    """
    exigidas = COLUNAS_MINIMAS.get(processador)
    if not exigidas:
        log.info("tse_validacao_sem_regra", processador=processador)
        return {"processador": processador, "validado": False, "colunas": []}

    presentes = ler_cabecalho(zip_path)
    faltando = [c for c in exigidas if c not in presentes]

    if faltando:
        log.error(
            "tse_estrutura_mudou",
            processador=processador, arquivo=zip_path.name,
            faltando=faltando, encontradas=len(presentes),
        )
        raise EstruturaInesperadaError(
            f"O arquivo do TSE mudou de estrutura: faltam as colunas "
            f"{', '.join(faltando)}. O arquivo tem {len(presentes)} colunas. "
            f"Nada foi importado — corrija o mapeamento antes de repetir."
        )

    novas = [c for c in presentes if c not in exigidas]
    log.info(
        "tse_estrutura_ok",
        processador=processador, arquivo=zip_path.name,
        colunas=len(presentes), colunas_novas=len(novas),
    )
    return {
        "processador": processador,
        "validado": True,
        "colunas": len(presentes),
        "colunas_novas": novas[:10],
    }


def cobertura(db: Session, *, ano: int, cargo: int | None = None) -> dict[str, Any]:
    """O que ja entrou e o que falta, por UF.

    Existe porque "o job terminou" nao quer dizer "o dado esta completo". Na
    apuracao o TSE libera a capital antes da cidade pequena, e sem este numero
    ninguem distingue uma importacao inteira de uma pela metade.

    `municipios_esperados` sai da propria tabela de municipios (o que o TSE ja
    nos deu algum dia), nao de uma constante — assim nao envelhece.
    """
    # "ZZ" e o codigo do TSE para o EXTERIOR: 189 cidades onde brasileiro vota
    # fora do pais. E dado legitimo, mas la so se vota em cargo federal — contar
    # essas 189 como "faltando" numa apuracao municipal inflaria o numero e
    # tiraria a confianca justamente na noite em que ele precisa ser confiavel.
    # Entra em `exterior`, separado, em vez de sumir sem explicacao.
    esperados = dict(
        db.execute(
            select(Municipality.state, func.count())
            .where(Municipality.state != "ZZ")
            .group_by(Municipality.state)
        ).all()
    )

    stmt = (
        select(Municipality.state, func.count(func.distinct(Municipality.id)))
        .select_from(VoteResult)
        .join(Municipality, Municipality.id == VoteResult.municipality_id)
        .join(Candidate, Candidate.id == VoteResult.candidate_id)
        .join(Election, Election.id == Candidate.election_id)
        .where(Election.year == ano)
        .group_by(Municipality.state)
    )
    if cargo is not None:
        stmt = stmt.where(Candidate.office_code == cargo)
    com_dado = dict(db.execute(stmt).all())

    linhas = []
    for uf in sorted(esperados):
        tem = com_dado.get(uf, 0)
        total = esperados[uf]
        linhas.append({
            "uf": uf,
            "municipios_com_dado": tem,
            "municipios_esperados": total,
            "faltam": total - tem,
            "pct": round(100 * tem / total, 1) if total else 0.0,
        })

    completas = sum(1 for l in linhas if l["faltam"] == 0)
    faltando_total = sum(l["faltam"] for l in linhas)

    log.info(
        "tse_cobertura",
        ano=ano, cargo=cargo, ufs_completas=completas,
        ufs=len(linhas), municipios_faltando=faltando_total,
    )
    return {
        "ano": ano,
        "cargo": cargo,
        # Fora da conta de propósito — ver o comentario em `esperados`.
        "exterior": {
            "cidades": db.execute(
                select(func.count()).select_from(Municipality)
                .where(Municipality.state == "ZZ")
            ).scalar() or 0,
            "nota": "Codigo ZZ do TSE: brasileiros votando fora do pais, onde "
                    "so ha cargo federal. Nao entra na cobertura.",
        },
        "ufs_completas": completas,
        "ufs_total": len(linhas),
        "municipios_faltando": faltando_total,
        "situacao": (
            "completo" if faltando_total == 0
            else "parcial" if completas
            else "vazio"
        ),
        "por_uf": linhas,
    }


def arquivos_prontos(diretorio: Path) -> list[dict[str, Any]]:
    """O que ja esta na porta de entrada manual, esperando ingestao.

    O TSE bloqueia download automatizado (403) desde 31/08/2026, entao na
    apuracao os arquivos podem chegar baixados a mao. Esta funcao existe pra
    responder "o arquivo chegou?" sem ninguem precisar entrar no servidor.
    """
    if not diretorio.exists():
        return []
    itens = []
    for caminho in sorted(diretorio.glob("*.zip")):
        try:
            tamanho = caminho.stat().st_size
        except OSError:
            continue
        itens.append({
            "dataset": caminho.stem,
            "arquivo": caminho.name,
            "tamanho_mb": round(tamanho / 1024 / 1024, 1),
            "valido": zipfile.is_zipfile(caminho),
        })
    return itens


__all__ = [
    "validar_estrutura", "cobertura", "arquivos_prontos",
    "EstruturaInesperadaError", "COLUNAS_MINIMAS", "ler_cabecalho",
]
