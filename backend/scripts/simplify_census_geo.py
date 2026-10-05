"""
Simplifica (Douglas-Peucker via shapely, preserve_topology) e arredonda a
geometria dos SETORES em census_geo, IN PLACE. Corta a contagem de vértices —
reduz o payload de /census/setores (baixado toda vez que se abre um município,
pra popular os painéis/agregação) e deixa o mapa de setores (opt-in) mais leve.

Conservador e idempotente: tolerância pequena (imperceptível no zoom de cidade),
e nunca substitui por geometria vazia/inválida (mantém a original em caso de erro).

Rodar DENTRO do container api (tem shapely):
    # 1) medir sem mutar:
    docker compose exec -T -e DRYRUN=1 api python scripts/simplify_census_geo.py
    # 2) aplicar:
    docker compose exec -T api python scripts/simplify_census_geo.py

Env:
    TOL     tolerância em graus (default 0.00006 ≈ 6-7 m)
    ND      casas decimais das coords (default 5 ≈ 1 m) — mesmo do ingest
    UF      prefixo de cd_mun p/ limitar (ex.: "33"); vazio = todos
    DRYRUN  "1" = só mede a redução, não grava
"""
import json
import os

from shapely.geometry import mapping, shape
from sqlalchemy import text

from app.core.database import SessionLocal

TOL = float(os.environ.get("TOL", "0.00006"))
ND = int(os.environ.get("ND", "5"))
UF = os.environ.get("UF", "")
DRYRUN = os.environ.get("DRYRUN") == "1"


def _round(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(obj[0]), ND), round(float(obj[1]), ND)]
        return [_round(x) for x in obj]
    return obj


def _count(coords) -> int:
    n = 0
    stack = [coords]
    while stack:
        o = stack.pop()
        if isinstance(o, (list, tuple)):
            if o and isinstance(o[0], (int, float)):
                n += 1
            else:
                stack.extend(o)
    return n


def main() -> None:
    db = SessionLocal()
    where = "level='setor' AND geometry IS NOT NULL"
    params: dict = {}
    if UF:
        where += " AND cd_mun LIKE :u"
        params["u"] = UF + "%"
    rows = db.execute(
        text(f"SELECT cd_setor, geometry FROM census_geo WHERE {where}"), params
    ).all()
    print(f"{len(rows)} setores | TOL={TOL} ND={ND} DRYRUN={DRYRUN}")

    before = after = done = skipped = 0
    for cd, geomj in rows:
        try:
            g = shape(geomj)
            gs = g.simplify(TOL, preserve_topology=True)
            if gs.is_empty or not gs.is_valid:
                gs = g  # não arrisca: mantém o original
            m = mapping(gs)
            m = {"type": m["type"], "coordinates": _round(m["coordinates"])}
            before += _count(geomj.get("coordinates"))
            after += _count(m["coordinates"])
            if not DRYRUN:
                db.execute(
                    text("UPDATE census_geo SET geometry=CAST(:g AS jsonb) WHERE cd_setor=:cd"),
                    {"g": json.dumps(m), "cd": cd},
                )
                done += 1
                if done % 500 == 0:
                    db.commit()
                    print(f"  ... {done} atualizados")
        except Exception as e:  # noqa: BLE001
            skipped += 1
            print(f"  skip {cd}: {e}")
    if not DRYRUN:
        db.commit()
    pct = (100 * (before - after) / before) if before else 0
    print(f"vértices: {before:,} -> {after:,} ({pct:.0f}% menos) | atualizados={done} skip={skipped}")


if __name__ == "__main__":
    main()
