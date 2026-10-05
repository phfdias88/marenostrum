"""Comparecimento, abstencao, brancos e nulos — gravar e ler.

DUAS FONTES, UMA TABELA (tse_turnout):

  * `do_feed` le o arquivo do canal AO VIVO do TSE (o mesmo do placar);
  * `importar_detalhe` le o `detalhe_votacao_munzona`, que o TSE publica para
    as eleicoes ja fechadas.

OS TRES PERCENTUAIS, e por que cada um tem o seu denominador:

  * ABSTENCAO = abstencoes / (comparecimento + abstencoes). Nao se usa o
    eleitorado total: durante a apuracao ele inclui as secoes que ainda nao
    chegaram, e a abstencao sairia artificialmente baixa.
  * BRANCOS e NULOS = votos / TOTAL DE VOTOS do cargo. Nao e o comparecimento:
    no Senado em ano de duas vagas cada eleitor da dois votos, e dividir pelo
    comparecimento daria o dobro do percentual real. E nao e validos + brancos
    + nulos: falta o voto ANULADO (candidato indeferido ou sub judice), que nao
    e valido nem nulo — governador do RJ em 2026 saia 5,24% de brancos contra
    os 5,09% do TSE. O total vem pronto da fonte ("tv" no canal ao vivo,
    QT_VOTOS no arquivo).

Conferido contra o que o TSE divulga: presidente 2018 da 20,33 / 2,65 / 6,14 e
2022 da 20,95 / 1,59 / 2,82.
"""
from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tse.turnout import TseTurnout
from app.services.tse_live import _i, _insert_do_dialeto
from app.utils.agg_cache import cached_agg

log = structlog.get_logger("marenostrum.services.comparecimento")

PAIS = "BR"

_CAMPOS = (
    "electorate", "turnout", "abstention", "valid_votes", "blank_votes",
    "null_votes", "total_votes", "sections_total", "sections_counted",
)

# Coluna do detalhe_votacao_munzona -> campo da tabela. Sao as colunas TOTAL_:
# as sem "TOTAL" deixam de fora o voto de legenda e o nulo tecnico.
_COLUNAS_DO_DETALHE = {
    "QT_APTOS": "electorate",
    "QT_COMPARECIMENTO": "turnout",
    "QT_ABSTENCOES": "abstention",
    "QT_TOTAL_VOTOS_VALIDOS": "valid_votes",
    "QT_VOTOS_BRANCOS": "blank_votes",
    "QT_TOTAL_VOTOS_NULOS": "null_votes",
    "QT_VOTOS": "total_votes",
    "QT_TOTAL_SECOES": "sections_total",
}


# ------------------------------------------------------------------ gravar

def do_feed(dado: dict) -> dict[str, int] | None:
    """Numeros de comparecimento de um arquivo do canal ao vivo.

    Devolve None se o arquivo ainda nao traz os blocos — acontece no comeco da
    apuracao, antes da primeira secao. Gravar zeros ali apagaria o que ja
    houvesse."""
    e = dado.get("e") or {}
    v = dado.get("v") or {}
    s = dado.get("s") or {}
    if not e or not v:
        return None
    return {
        "electorate": _i(e.get("te")),
        "turnout": _i(e.get("c")),
        "abstention": _i(e.get("a")),
        "valid_votes": _i(v.get("vv")),
        "blank_votes": _i(v.get("vb")),
        "null_votes": _i(v.get("tvn")),
        "total_votes": _i(v.get("tv")),
        "sections_total": _i(s.get("ts")),
        "sections_counted": _i(s.get("st")),
    }


def gravar(
    db: Session, *, ano: int, turno: int, cargo: int, uf: str,
    numeros: dict[str, int],
) -> None:
    """Grava (ou SUBSTITUI) a linha daquele cargo naquela UF.

    Substitui em vez de somar: o feed entrega o acumulado, e a captura roda de
    dois em dois minutos a noite inteira."""
    agora = datetime.now(timezone.utc)
    valores = {c: numeros.get(c) for c in _CAMPOS}
    stmt = _insert_do_dialeto(db)(TseTurnout.__table__).values(
        id=uuid4(), year=ano, round=turno, office_code=cargo, uf=uf.upper(),
        created_at=agora, updated_at=agora, **valores,
    )
    db.execute(stmt.on_conflict_do_update(
        index_elements=["year", "round", "office_code", "uf"],
        set_={**valores, "updated_at": agora},
    ))


def importar_detalhe(db: Session, zip_path: Path, *, ano: int) -> dict[str, int]:
    """Soma o detalhe_votacao_munzona por turno, cargo e UF e grava.

    O arquivo vem por municipio e zona; aqui so interessa o total da UF. O
    exterior aparece como UF 'ZZ' e entra na soma do pais — sem ele o total de
    presidente nao bate com o oficial."""
    soma: dict[tuple[int, int, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    lidas = 0
    with zipfile.ZipFile(zip_path) as z:
        nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
        # O zip traz um CSV por UF mais o _BRASIL com tudo: ler os dois dobraria.
        nacionais = [n for n in nomes if "_brasil" in n.lower()]
        for nome in (nacionais or nomes):
            with z.open(nome) as f:
                leitor = csv.DictReader(
                    io.TextIOWrapper(f, encoding="latin-1"), delimiter=";",
                )
                faltando = set(_COLUNAS_DO_DETALHE) - set(leitor.fieldnames or [])
                if faltando:
                    raise ValueError(
                        f"{nome}: o TSE mudou o formato, faltam as colunas "
                        f"{sorted(faltando)}"
                    )
                for row in leitor:
                    uf = (row.get("SG_UF") or "").strip().upper()
                    cargo = _i(row.get("CD_CARGO"))
                    if not uf or not cargo:
                        continue
                    lidas += 1
                    alvo = soma[(_i(row.get("NR_TURNO")) or 1, cargo, uf)]
                    for coluna, campo in _COLUNAS_DO_DETALHE.items():
                        alvo[campo] += _i(row.get(coluna))

    for (turno, cargo, uf), numeros in soma.items():
        # Eleicao fechada: toda secao que existe foi apurada.
        numeros["sections_counted"] = numeros["sections_total"]
        gravar(db, ano=ano, turno=turno, cargo=cargo, uf=uf, numeros=numeros)
    db.commit()

    log.info("comparecimento_importado", ano=ano, linhas=lidas, gravadas=len(soma))
    return {"linhas_lidas": lidas, "gravadas": len(soma)}


# --------------------------------------------------------------------- ler

def _pct(parte: int, todo: int) -> float | None:
    return round(100 * parte / todo, 2) if todo > 0 else None


def resumir(ano: int, n: dict[str, int]) -> dict[str, Any]:
    """Uma linha da serie, com os percentuais ja calculados (ver topo)."""
    # Linha gravada antes de existir o total: a soma e a melhor aproximacao.
    votos = n.get("total_votes") or (
        n["valid_votes"] + n["blank_votes"] + n["null_votes"]
    )
    total_secoes = n.get("sections_total") or 0
    apuradas = n.get("sections_counted") or 0
    return {
        "ano": ano,
        "eleitorado": n["electorate"],
        "comparecimento": n["turnout"],
        "abstencao": n["abstention"],
        "validos": n["valid_votes"],
        "brancos": n["blank_votes"],
        "nulos": n["null_votes"],
        # Votos que nao sao validos, brancos nem nulos: os anulados.
        "anulados": max(
            0, votos - n["valid_votes"] - n["blank_votes"] - n["null_votes"]
        ),
        "pct_abstencao": _pct(n["abstention"], n["turnout"] + n["abstention"]),
        "pct_brancos": _pct(n["blank_votes"], votos),
        "pct_nulos": _pct(n["null_votes"], votos),
        "secoes_total": total_secoes or None,
        "secoes_apuradas": apuradas or None,
        "pct_secoes": _pct(apuradas, total_secoes),
        # Sem dado de secao nao da para afirmar que esta parcial.
        "parcial": bool(total_secoes) and apuradas < total_secoes,
    }


def get_turnout(
    db: Session, *, cargo: int, uf: str = PAIS, turno: int = 1,
) -> dict[str, Any]:
    uf = (uf or PAIS).strip().upper()
    return cached_agg(
        f"comparecimento:{cargo}:{uf}:{turno}",
        lambda: _calcular(db, cargo, uf, turno),
    )


def _calcular(db: Session, cargo: int, uf: str, turno: int) -> dict[str, Any]:
    linhas = db.execute(
        select(TseTurnout).where(
            TseTurnout.office_code == cargo, TseTurnout.round == turno,
        )
    ).scalars().all()

    por_ano: dict[int, dict[str, dict[str, int]]] = defaultdict(dict)
    for l in linhas:
        por_ano[l.year][l.uf] = {c: getattr(l, c) or 0 for c in _CAMPOS}

    anos = []
    for ano in sorted(por_ano):
        ufs = por_ano[ano]
        if uf in ufs:
            numeros = ufs[uf]
        elif uf == PAIS and ufs:
            # O pais sem linha propria e a soma das UFs (com o exterior). E o
            # caso das eleicoes fechadas e, na apuracao, de todo cargo que nao
            # seja presidente — o TSE so publica arquivo nacional para ele.
            numeros = {c: sum(n[c] for n in ufs.values()) for c in _CAMPOS}
        else:
            continue
        anos.append(resumir(ano, numeros))

    return {"cargo": cargo, "uf": uf, "turno": turno, "anos": anos}
