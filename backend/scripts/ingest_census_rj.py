"""
POC RJ inteiro: ingere TODOS os setores censitários do RJ (IBGE Censo 2022)
+ a camada de municípios (geometria via malha API + agregados do censo) para a
visão estadual com drill-down (estado -> município -> setor).

Coordenadas arredondadas a 5 casas (~1 m) pra reduzir o payload servido.

Pré: /tmp/rj_setores.zip e /tmp/basico.zip baixados do IBGE.
Rode dentro do container api (precisa de pyshp + httpx).
"""
import io
import json
import zipfile

import httpx
import shapefile  # pyshp
from sqlalchemy import text

from app.core.database import SessionLocal

import os
SETOR_ZIP = os.environ.get("SETOR_ZIP", "/tmp/rj_setores.zip")
BASICO_ZIP = os.environ.get("BASICO_ZIP", "/tmp/basico.zip")
UF = os.environ.get("UF", "33")  # 33=RJ, 35=SP...
ND = 5     # casas decimais nas coordenadas


def _num(s):
    try:
        return int(float(str(s).strip().strip('"').replace(",", ".")))
    except Exception:
        return None


def _fix(s):
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except Exception:
        return s


def _round(obj):
    """Arredonda recursivamente as coordenadas do GeoJSON."""
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(obj[0]), ND), round(float(obj[1]), ND)]
        return [_round(x) for x in obj]
    return obj


def load_census() -> dict:
    z = zipfile.ZipFile(BASICO_ZIP)
    name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    lines = z.read(name).decode("latin-1").splitlines()
    hdr = [h.strip('"') for h in lines[0].split(";")]
    i_setor, i_uf = hdr.index("CD_SETOR"), hdr.index("CD_UF")
    i_v1, i_v2 = hdr.index("v0001"), hdr.index("v0002")
    out = {}
    for ln in lines[1:]:
        p = ln.split(";")
        if p[i_uf].strip('"') != UF:
            continue
        out[p[i_setor].strip('"')] = (_num(p[i_v1]), _num(p[i_v2]))
    return out


def ingest_setores(db, census):
    z = zipfile.ZipFile(SETOR_ZIP)
    base = [n for n in z.namelist() if n.lower().endswith(".shp")][0][:-4]
    r = shapefile.Reader(
        shp=io.BytesIO(z.read(base + ".shp")),
        dbf=io.BytesIO(z.read(base + ".dbf")),
        shx=io.BytesIO(z.read(base + ".shx")),
        encoding="latin-1",
    )
    flds = [f[0] for f in r.fields[1:]]

    def gi(rec, name):
        return rec[flds.index(name)] if name in flds else None

    db.execute(text("DELETE FROM census_geo WHERE level='setor' AND cd_mun LIKE :u"),
               {"u": UF + "%"})
    db.commit()

    n = 0
    for sr in r.iterShapeRecords():
        rec = sr.record
        cd = str(gi(rec, "CD_SETOR"))
        pop, dom = census.get(cd, (None, None))
        geom = sr.shape.__geo_interface__
        geom = {"type": geom["type"], "coordinates": _round(geom["coordinates"])}
        area = gi(rec, "AREA_KM2")
        try:
            area = float(str(area).replace(",", ".")) if area not in (None, "") else None
        except Exception:
            area = None
        db.execute(
            text(
                "INSERT INTO census_geo "
                "(level, cd_setor, cd_mun, nm_mun, cd_dist, nm_dist, nm_subdist, "
                " nm_bairro, situacao, area_km2, populacao, domicilios, geometry) "
                "VALUES ('setor',:cd,:mun,:nmun,:dist,:ndist,:subd,:bai,:sit,:area,"
                " :pop,:dom, CAST(:geom AS jsonb)) "
                "ON CONFLICT (cd_setor) DO UPDATE SET populacao=:pop, "
                " domicilios=:dom, geometry=CAST(:geom AS jsonb)"
            ),
            {
                "cd": cd, "mun": str(gi(rec, "CD_MUN")), "nmun": _fix(gi(rec, "NM_MUN")),
                "dist": str(gi(rec, "CD_DIST") or ""), "ndist": _fix(gi(rec, "NM_DIST")),
                "subd": _fix(gi(rec, "NM_SUBDIST")), "bai": _fix(gi(rec, "NM_BAIRRO") or ""),
                "sit": _fix(gi(rec, "SITUACAO")), "area": area,
                "pop": pop, "dom": dom, "geom": json.dumps(geom),
            },
        )
        n += 1
        if n % 500 == 0:
            db.commit()
            print(f"  ... {n} setores")
    db.commit()
    print(f"setores RJ inseridos: {n}")


def ingest_municipios(db):
    """Camada de municípios: geometria (malha API IBGE) + agregados do censo."""
    url = (
        f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{UF}"
        "?formato=application/vnd.geo+json&intrarregiao=municipio&qualidade=intermediaria"
    )
    with httpx.Client(timeout=120) as c:
        fc = c.get(url).json()
    print(f"malha de municípios RJ: {len(fc['features'])} features")

    # Agregados do censo por município (a partir dos setores já carregados)
    agg = {
        row[0]: (row[1], row[2], row[3], row[4], row[5])
        for row in db.execute(text(
            "SELECT cd_mun, max(nm_mun), coalesce(sum(populacao),0), "
            "coalesce(sum(domicilios),0), count(*), count(distinct nm_dist) "
            "FROM census_geo WHERE level='setor' AND cd_mun LIKE :u GROUP BY cd_mun"
        ), {"u": UF + "%"}).all()
    }

    db.execute(text("DELETE FROM census_geo WHERE level='municipio' AND cd_mun LIKE :u"),
               {"u": UF + "%"})
    db.commit()

    n = 0
    for ft in fc["features"]:
        cod = str(ft.get("properties", {}).get("codarea", "")).strip()
        if cod not in agg:
            continue
        nm, pop, dom, setores, distritos = agg[cod]
        geom = ft["geometry"]
        geom = {"type": geom["type"], "coordinates": _round(geom["coordinates"])}
        db.execute(
            text(
                "INSERT INTO census_geo "
                "(level, cd_setor, cd_mun, nm_mun, populacao, domicilios, geometry) "
                "VALUES ('municipio', :k, :mun, :nm, :pop, :dom, CAST(:geom AS jsonb)) "
                "ON CONFLICT (cd_setor) DO UPDATE SET populacao=:pop, domicilios=:dom, "
                "geometry=CAST(:geom AS jsonb), nm_mun=:nm"
            ),
            {"k": "MUN" + cod, "mun": cod, "nm": nm, "pop": pop, "dom": dom,
             "geom": json.dumps(geom)},
        )
        n += 1
    db.commit()
    print(f"municípios RJ inseridos: {n}")


def main():
    db = SessionLocal()
    census = load_census()
    print(f"censo: {len(census)} setores do RJ no CSV básico")
    ingest_setores(db, census)
    ingest_municipios(db)
    chk = db.execute(text(
        "SELECT count(*) FILTER (WHERE level='setor'), "
        "count(*) FILTER (WHERE level='municipio'), "
        "coalesce(sum(populacao) FILTER (WHERE level='setor'),0) "
        "FROM census_geo WHERE cd_mun LIKE :u"
    ), {"u": UF + "%"}).first()
    print(f"FINAL: setores={chk[0]} municipios={chk[1]} populacao_total_RJ={chk[2]:,}")


if __name__ == "__main__":
    main()
