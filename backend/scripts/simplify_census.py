"""
Simplifica as geometrias dos setores censitários (Douglas-Peucker) direto no
banco, reduzindo o nº de vértices → mapa renderiza muito mais rápido (sobretudo
cidades grandes como o Rio). Mantém a forma reconhecível (~13 m de tolerância).

Idempotente: re-rodar sobre geometria já simplificada quase não muda nada.
Rode dentro do container api.
"""
import json

from sqlalchemy import text

from app.core.database import SessionLocal

EPS = 0.00012   # ~13 m em graus
ND = 5          # casas decimais


def _dp(points, eps):
    """Douglas-Peucker iterativo (sem recursão) numa polilinha aberta."""
    n = len(points)
    if n < 3:
        return points
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        ax, ay = points[s]
        bx, by = points[e]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        dmax, idx = 0.0, -1
        for i in range(s + 1, e):
            px, py = points[i]
            d = abs(dx * (ay - py) - (ax - px) * dy) / norm
            if d > dmax:
                dmax, idx = d, i
        if dmax > eps and idx != -1:
            keep[idx] = True
            stack.append((s, idx))
            stack.append((idx, e))
    return [points[i] for i in range(n) if keep[i]]


def _dp_ring(ring, eps):
    """DP num anel fechado (1º == último ponto)."""
    if len(ring) < 6:
        return ring
    pts = ring[:-1]  # abre o anel
    a = pts[0]
    # 2º âncora: ponto mais distante do início — evita colapsar o anel
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - a[0]) ** 2 + (pts[i][1] - a[1]) ** 2)
    arc1 = _dp(pts[: far + 1], eps)
    arc2 = _dp(pts[far:] + [pts[0]], eps)
    merged = arc1[:-1] + arc2
    if merged[0] != merged[-1]:
        merged.append(merged[0])
    return merged if len(merged) >= 4 else ring


def _round(pt):
    return [round(pt[0], ND), round(pt[1], ND)]


def _simplify_geom(geom):
    t = geom["type"]
    if t == "Polygon":
        rings = [[_round(p) for p in _dp_ring(r, EPS)] for r in geom["coordinates"]]
        return {"type": "Polygon", "coordinates": rings}
    if t == "MultiPolygon":
        polys = [[[_round(p) for p in _dp_ring(r, EPS)] for r in poly]
                 for poly in geom["coordinates"]]
        return {"type": "MultiPolygon", "coordinates": polys}
    return geom


def _count(geom):
    c = 0
    co = geom.get("coordinates", [])

    def walk(x):
        nonlocal c
        if isinstance(x, (list, tuple)):
            if x and isinstance(x[0], (int, float)):
                c += 1
            else:
                for y in x:
                    walk(y)
    walk(co)
    return c


def main():
    db = SessionLocal()
    rows = db.execute(text(
        "SELECT cd_setor, geometry FROM census_geo WHERE level='setor' ORDER BY cd_setor"
    )).all()
    print(f"setores a simplificar: {len(rows)}")

    before = after = 0
    n = 0
    for cd, geom in rows:
        if isinstance(geom, str):
            geom = json.loads(geom)
        before += _count(geom)
        simp = _simplify_geom(geom)
        after += _count(simp)
        db.execute(
            text("UPDATE census_geo SET geometry=CAST(:g AS jsonb) WHERE cd_setor=:c"),
            {"g": json.dumps(simp), "c": cd},
        )
        n += 1
        if n % 1000 == 0:
            db.commit()
            print(f"  ... {n} setores")
    db.commit()
    pct = 100 * (1 - after / before) if before else 0
    print(f"FINAL: {n} setores · vértices {before:,} -> {after:,} (-{pct:.1f}%)")


if __name__ == "__main__":
    main()
