#!/usr/bin/env python3
"""
Materializa o vencedor por municipio (tabela tse_winners_map, migration 062).

POR QUE EXISTE: calcular na hora custava 164s para Deputado Federal 2022 — o
DISTINCT ON ordenava 3,3 milhoes de linhas em disco para devolver 5.570. Aqui
o mesmo trabalho e feito UMA vez por (ano, cargo), fora do caminho do usuario.

COMO PROCESSA: uma combinacao ano+cargo por vez, com commit entre elas. Fazer
tudo numa transacao so ocuparia memoria e seguraria lock por minutos num
servidor de 1 vCPU; assim, se cair no meio, o que ja entrou vale e rodar de
novo completa (o upsert e idempotente).

QUANDO RODAR: depois de cada import do TSE. Sem isso o mapa mostra o resultado
da carga anterior — silenciosamente, que e o pior tipo de dado errado.

USO:
    docker compose cp backend/scripts/refresh_tse_winners_map.py api:/tmp/
    docker compose exec -T -e PYTHONPATH=/app api \
        python /tmp/refresh_tse_winners_map.py            # tudo
    ... python /tmp/refresh_tse_winners_map.py --year 2024 # so um ano
"""
from __future__ import annotations

import argparse
import sys
import time

import structlog
from sqlalchemy import text

from app.core.database import SessionLocal

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)
log = structlog.get_logger("tse.winners_map")

# DISTINCT ON resolve "o mais votado de cada municipio". O desempate por
# urn_name e o mesmo do endpoint antigo: sem ele, empate tecnico devolvia
# vencedor aleatorio e o municipio trocava de cor a cada carga.
UPSERT = text("""
INSERT INTO tse_winners_map (
    year, office_code, municipality_id, candidate_id, urn_name,
    party_abbr, party_number, votes, latitude, longitude, municipality, state
)
SELECT DISTINCT ON (vr.municipality_id)
       :year, :office, vr.municipality_id, c.id, c.urn_name,
       p.abbreviation, p.number, vr.votes, m.latitude, m.longitude, m.name, m.state
FROM tse_vote_results vr
JOIN tse_candidates c ON c.id = vr.candidate_id
JOIN tse_elections  e ON e.id = c.election_id
JOIN tse_parties    p ON p.id = c.party_id
JOIN tse_municipalities m ON m.id = vr.municipality_id
WHERE e.year = :year AND c.office_code = :office AND vr.votes > 0
ORDER BY vr.municipality_id, vr.votes DESC, c.urn_name ASC
ON CONFLICT (year, office_code, municipality_id) DO UPDATE SET
    candidate_id = EXCLUDED.candidate_id,
    urn_name     = EXCLUDED.urn_name,
    party_abbr   = EXCLUDED.party_abbr,
    party_number = EXCLUDED.party_number,
    votes        = EXCLUDED.votes,
    latitude     = EXCLUDED.latitude,
    longitude    = EXCLUDED.longitude,
    municipality = EXCLUDED.municipality,
    state        = EXCLUDED.state,
    updated_at   = now()
""")


def main() -> int:
    p = argparse.ArgumentParser(description="Materializa o vencedor por municipio.")
    p.add_argument("--year", type=int, help="processa so este ano")
    args = p.parse_args()

    db = SessionLocal()
    try:
        # Agregacao pesada em servidor com statement_timeout curto morre no meio.
        db.execute(text("SET statement_timeout = 0"))
        db.commit()

        combos = db.execute(text("""
            SELECT DISTINCT e.year, c.office_code
            FROM tse_candidates c
            JOIN tse_elections e ON e.id = c.election_id
            WHERE c.office_code IS NOT NULL
              -- CAST explicito: sem ele o Postgres nao consegue inferir o tipo
              -- do parametro em ":year IS NULL" e falha com AmbiguousParameter.
              AND (CAST(:year AS integer) IS NULL OR e.year = CAST(:year AS integer))
            ORDER BY e.year DESC, c.office_code
        """), {"year": args.year}).all()
        log.info("combinacoes_a_processar", total=len(combos))

        t0 = time.perf_counter()
        gravadas = 0
        for i, (year, office) in enumerate(combos, start=1):
            t1 = time.perf_counter()
            res = db.execute(UPSERT, {"year": year, "office": office})
            db.commit()  # uma combinacao por transacao (ver docstring)
            gravadas += res.rowcount or 0
            log.info("combinacao_pronta", i=f"{i}/{len(combos)}", ano=year,
                     cargo=office, municipios=res.rowcount,
                     segundos=round(time.perf_counter() - t1, 1))

        total, combos_tab = db.execute(text(
            "SELECT count(*), count(DISTINCT (year, office_code)) FROM tse_winners_map"
        )).first()
        log.info("concluido", linhas=total, combinacoes=combos_tab,
                 gravadas_agora=gravadas,
                 minutos=round((time.perf_counter() - t0) / 60, 1))
        return 0
    except KeyboardInterrupt:
        log.warning("interrompido", dica="pode rodar de novo: o upsert e idempotente")
        return 130
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
