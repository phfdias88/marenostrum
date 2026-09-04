#!/usr/bin/env python3
"""
Reconstroi os locais de votacao de UMA UF com a ZONA na identidade.

POR QUE EXISTE: ate a migration 064 o local era gravado com a chave
(ano, municipio, numero). No TSE o NR_LOCAL_VOTACAO so e unico DENTRO da zona
eleitoral, entao locais distintos de zonas diferentes colidiam e viravam uma
linha so — os votos somavam certo no total do municipio, mas o bairro de um
deles levava os votos de todos.

Medido no arquivo do TSE de 2024: o Rio tem 1.440 locais reais e estava com
163 no banco; 128 desses 163 misturavam mais de um bairro, e o pior juntava 33
(Barra da Tijuca, Botafogo e Campo Grande contando como o mesmo lugar). No
Brasil, a chave antiga apagava 11.283 locais (12,1%).

POR QUE UMA UF POR VEZ: apagar os locais de um ano derruba por cascata TODAS as
secoes daquele ano (6,8 milhoes em 2024). Fazendo estado por estado, a janela
sem dado de bairro dura minutos e atinge um estado, em vez de horas e o pais
inteiro.

SEQUENCIA POR UF (o script faz as tres coisas numa transacao):
  1. apaga os locais do ano naquela UF   -> as secoes caem por cascata
  2. insere os locais certos, com zona
  3. reimporta as secoes daquela UF      -> os votos voltam no lugar certo

Sem o zip de secoes o passo 3 nao acontece, e a UF fica SEM voto por bairro.
Por isso o script exige --zip-secoes, a menos que voce peca --so-medir.

USO:
    # so mede, nao altera nada
    docker compose exec -T -e PYTHONPATH=/app api \\
        python /tmp/corrigir_locais_zona.py --uf RJ --so-medir \\
        --zip-locais /tmp/locais2024.zip

    # aplica (exige os dois arquivos)
    docker compose exec -T -e PYTHONPATH=/app api \\
        python /tmp/corrigir_locais_zona.py --uf RJ \\
        --zip-locais /tmp/locais2024.zip --zip-secoes /tmp/secoes_rj.zip
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, insert, select

from app.core.database import SessionLocal
from app.models.tse import Municipality
from app.models.tse.section_vote import TseSectionVote
from app.models.tse.voting_place import TseVotingPlace

CHUNK = 5000


def _i(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _f(v):
    try:
        x = float(str(v).strip().replace(",", "."))
        return x if -90 <= x <= 90 or -180 <= x <= 180 else None
    except (TypeError, ValueError):
        return None


def _coord_ok(lat, lng) -> bool:
    return (
        lat is not None and lng is not None
        and -34 <= lat <= 6 and -74 <= lng <= -34
    )


def ler_locais(zip_path: Path, uf: str, ano: int) -> dict[tuple[int, int, int], dict]:
    """(cd_municipio, zona, local) -> dados do local, ja somando os eleitores."""
    z = zipfile.ZipFile(zip_path)
    nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    acc: dict[tuple[int, int, int], dict] = {}

    with z.open(nome) as f:
        leitor = csv.DictReader(
            io.TextIOWrapper(f, encoding="latin-1"), delimiter=";"
        )
        for row in leitor:
            if (row.get("SG_UF") or "").strip().upper() != uf:
                continue
            mun = _i(row.get("CD_MUNICIPIO"))
            zona = _i(row.get("NR_ZONA"))
            loc = _i(row.get("NR_LOCAL_VOTACAO"))
            if not mun or not zona or not loc:
                continue

            chave = (mun, zona, loc)
            eleitores = _i(row.get("QT_ELEITOR_SECAO")) or 0
            if chave in acc:
                acc[chave]["electors_total"] += eleitores
                continue

            acc[chave] = {
                "cd_municipio": mun,
                "year": ano,
                "zone": zona,
                "local_code": loc,
                "name": (row.get("NM_LOCAL_VOTACAO") or "")[:200],
                "address": (row.get("DS_ENDERECO") or "")[:300] or None,
                "neighborhood": (row.get("NM_BAIRRO") or "").strip()[:120] or None,
                "latitude": _f(row.get("NR_LATITUDE")),
                "longitude": _f(row.get("NR_LONGITUDE")),
                "electors_total": eleitores,
            }
    return acc


def importar_secoes(db, zip_path: Path, *, uf: str, ano: int) -> None:
    """Carrega o voto por secao SEM agregar em Python.

    O importador da aplicacao acumula tudo num dicionario antes de gravar. Para
    o RJ isso coube (875 mil chaves), para SP nao caberia: o CSV tem 2,5 GB e a
    agregacao passaria de 800 MB num container de 768 MB — e o arquivo nao vem
    agrupado por municipio, entao nem descarregar por bloco resolveria.

    Aqui as linhas cruas vao para uma tabela de trabalho via COPY e quem soma e
    o Postgres, que faz isso em disco. A memoria fica constante, independente do
    tamanho da UF.
    """
    conn = db.connection().connection            # psycopg cru, para o COPY
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_secoes")
        cur.execute(
            "CREATE UNLOGGED TABLE tmp_secoes ("
            " sq bigint, muni int, zona int, local int, votos int)"
        )

        z = zipfile.ZipFile(zip_path)
        nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        lidas = descartadas = copiadas = 0

        with z.open(nome) as f, cur.copy(
            "COPY tmp_secoes (sq, muni, zona, local, votos) FROM STDIN"
        ) as cp:
            leitor = csv.DictReader(
                io.TextIOWrapper(f, encoding="latin-1"), delimiter=";"
            )
            for row in leitor:
                lidas += 1
                # APENAS 1o turno: o mesmo SQ aparece nos dois turnos e somar os
                # dois dobraria o voto da secao (mesma regra do importador da app).
                if (_i(row.get("NR_TURNO")) or 1) != 1:
                    descartadas += 1
                    continue
                sq = _i(row.get("SQ_CANDIDATO"))
                mun = _i(row.get("CD_MUNICIPIO"))
                zona = _i(row.get("NR_ZONA"))
                loc = _i(row.get("NR_LOCAL_VOTACAO"))
                votos = _i(row.get("QT_VOTOS"))
                if None in (sq, mun, zona, loc, votos):
                    descartadas += 1
                    continue
                cp.write_row((sq, mun, zona, loc, votos))
                copiadas += 1
                if copiadas % 2_000_000 == 0:
                    print(f"    {copiadas:,} linhas copiadas".replace(",", "."), flush=True)

        print(f"  lidas {lidas:,} / copiadas {copiadas:,} / descartadas {descartadas:,}"
              .replace(",", "."), flush=True)

        cur.execute("CREATE INDEX ON tmp_secoes (muni, zona, local)")
        cur.execute("ANALYZE tmp_secoes")

        print("  somando no banco...", flush=True)
        cur.execute(
            """
            INSERT INTO tse_section_votes
                (id, candidate_id, voting_place_id, votes, created_at, updated_at)
            SELECT gen_random_uuid(), c.id, vp.id, SUM(t.votos), now(), now()
            FROM tmp_secoes t
            JOIN tse_municipalities m ON m.tse_code = t.muni AND m.state = %s
            JOIN tse_voting_places vp
              ON vp.municipality_id = m.id AND vp.year = %s
             AND vp.zone = t.zona AND vp.local_code = t.local
            JOIN tse_candidates c ON c.sq_candidato = t.sq
            GROUP BY c.id, vp.id
            """,
            (uf, ano),
        )
        print(f"  {cur.rowcount:,} linhas de voto gravadas".replace(",", "."), flush=True)
        cur.execute("DROP TABLE tmp_secoes")
    db.commit()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--uf", required=True)
    p.add_argument("--ano", type=int, default=2024)
    p.add_argument("--zip-locais", required=True)
    p.add_argument("--zip-secoes")
    p.add_argument("--so-medir", action="store_true")
    args = p.parse_args()

    uf = args.uf.strip().upper()
    if not args.so_medir and not args.zip_secoes:
        print(
            "ERRO: sem --zip-secoes a UF ficaria sem voto por bairro depois da "
            "troca. Passe o arquivo de secoes, ou use --so-medir.",
            file=sys.stderr,
        )
        return 2

    db = SessionLocal()
    db.execute(select(func.set_config("statement_timeout", "0", True)))

    munis = {
        m.tse_code: m.id
        for m in db.execute(
            select(Municipality).where(Municipality.state == uf)
        ).scalars()
    }
    if not munis:
        print(f"ERRO: nenhum municipio na UF {uf}.", file=sys.stderr)
        return 2

    ids = list(munis.values())
    antes_locais = db.execute(
        select(func.count()).select_from(TseVotingPlace).where(
            TseVotingPlace.municipality_id.in_(ids),
            TseVotingPlace.year == args.ano,
        )
    ).scalar() or 0
    antes_secoes = db.execute(
        select(func.count()).select_from(TseSectionVote)
        .join(TseVotingPlace, TseVotingPlace.id == TseSectionVote.voting_place_id)
        .where(
            TseVotingPlace.municipality_id.in_(ids),
            TseVotingPlace.year == args.ano,
        )
    ).scalar() or 0

    print(f"[{uf} {args.ano}] lendo o arquivo do TSE...", flush=True)
    novos = ler_locais(Path(args.zip_locais), uf, args.ano)
    faltando = {k for k in novos if k[0] not in munis}
    usaveis = {k: v for k, v in novos.items() if k[0] in munis}

    print(f"  locais no banco hoje ....... {antes_locais:>8,}".replace(",", "."))
    print(f"  locais no arquivo do TSE ... {len(usaveis):>8,}".replace(",", "."))
    print(f"  ganho ...................... {len(usaveis) - antes_locais:>8,}".replace(",", "."))
    print(f"  secoes que cairao ......... {antes_secoes:>8,}".replace(",", "."))
    if faltando:
        print(f"  AVISO: {len(faltando)} locais de municipio nao cadastrado, ignorados")

    if args.so_medir:
        print("\n(--so-medir: nada foi alterado)")
        return 0

    agora = datetime.now(timezone.utc)
    linhas = [
        {
            "id": uuid4(),
            "year": v["year"],
            "zone": v["zone"],
            "local_code": v["local_code"],
            "municipality_id": munis[v["cd_municipio"]],
            "name": v["name"],
            "address": v["address"],
            "neighborhood": v["neighborhood"],
            "latitude": v["latitude"],
            "longitude": v["longitude"],
            "geo_source": "tse" if _coord_ok(v["latitude"], v["longitude"]) else "unmapped",
            "electors_total": v["electors_total"],
            "created_at": agora,
            "updated_at": agora,
        }
        for v in usaveis.values()
    ]

    print(f"\n[{uf}] trocando os locais...", flush=True)
    db.execute(
        delete(TseVotingPlace).where(
            TseVotingPlace.municipality_id.in_(ids),
            TseVotingPlace.year == args.ano,
        )
    )
    for i in range(0, len(linhas), CHUNK):
        db.execute(insert(TseVotingPlace), linhas[i : i + CHUNK])
    db.commit()
    print(f"  {len(linhas)} locais gravados, agora com zona.")

    print("")
    print("[" + uf + "] reimportando as secoes...", flush=True)
    importar_secoes(db, Path(args.zip_secoes), uf=uf, ano=args.ano)

    depois = db.execute(
        select(func.count()).select_from(TseSectionVote)
        .join(TseVotingPlace, TseVotingPlace.id == TseSectionVote.voting_place_id)
        .where(
            TseVotingPlace.municipality_id.in_(ids),
            TseVotingPlace.year == args.ano,
        )
    ).scalar() or 0
    print(f"\n[{uf}] pronto. secoes: {antes_secoes} -> {depois}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
