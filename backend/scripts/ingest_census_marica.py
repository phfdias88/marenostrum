"""
POC: ingere os setores censitários de Maricá/RJ (IBGE Censo 2022).

Lê a malha de setores do RJ (shapefile) + o agregado básico (população/
domicílios), filtra Maricá (CD_MUN 3302700) e grava em census_geo com a
geometria em GeoJSON. Rode dentro do container api (precisa de pyshp).

Pré: /tmp/rj_setores.zip e /tmp/basico.zip já baixados do IBGE.
"""
import io
import json
import zipfile

import shapefile  # pyshp
from sqlalchemy import text

from app.core.database import SessionLocal

SETOR_ZIP = "/tmp/rj_setores.zip"
BASICO_ZIP = "/tmp/basico.zip"
CD_MUN = "3302700"  # Maricá/RJ


def _num(s):
    try:
        return int(float(str(s).strip().strip('"').replace(",", ".")))
    except Exception:
        return None


def _fix(s):
    """Corrige nomes: lemos o DBF como latin-1 (byte-transparente), mas o IBGE
    grava em UTF-8. Re-encode latin-1 -> decode utf-8 conserta os acentos."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except Exception:
        return s


def load_census() -> dict:
    """CD_SETOR -> (populacao v0001, domicilios v0002)."""
    z = zipfile.ZipFile(BASICO_ZIP)
    name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    lines = z.read(name).decode("latin-1").splitlines()
    hdr = [h.strip('"') for h in lines[0].split(";")]
    i_setor, i_mun = hdr.index("CD_SETOR"), hdr.index("CD_MUN")
    i_v1, i_v2 = hdr.index("v0001"), hdr.index("v0002")
    out = {}
    for ln in lines[1:]:
        p = ln.split(";")
        if p[i_mun].strip('"') != CD_MUN:
            continue
        out[p[i_setor].strip('"')] = (_num(p[i_v1]), _num(p[i_v2]))
    return out


def main():
    census = load_census()
    print(f"censo: {len(census)} setores de Maricá no CSV básico")

    z = zipfile.ZipFile(SETOR_ZIP)
    base = [n for n in z.namelist() if n.lower().endswith(".shp")][0][:-4]
    # Lemos como latin-1 (preserva bytes) e corrigimos via _fix (IBGE é UTF-8).
    r = shapefile.Reader(
        shp=io.BytesIO(z.read(base + ".shp")),
        dbf=io.BytesIO(z.read(base + ".dbf")),
        shx=io.BytesIO(z.read(base + ".shx")),
        encoding="latin-1",
    )
    flds = [f[0] for f in r.fields[1:]]

    def gi(rec, name):
        return rec[flds.index(name)] if name in flds else None

    db = SessionLocal()
    db.execute(text("DELETE FROM census_geo WHERE cd_mun = :m"), {"m": CD_MUN})
    db.commit()

    n = 0
    for sr in r.iterShapeRecords():
        rec = sr.record
        if str(gi(rec, "CD_MUN")) != CD_MUN:
            continue
        cd = str(gi(rec, "CD_SETOR"))
        pop, dom = census.get(cd, (None, None))
        db.execute(
            text(
                "INSERT INTO census_geo "
                "(cd_setor, cd_mun, nm_mun, cd_dist, nm_dist, nm_subdist, "
                " nm_bairro, situacao, area_km2, populacao, domicilios, geometry) "
                "VALUES (:cd,:mun,:nmun,:dist,:ndist,:subd,:bai,:sit,:area,"
                " :pop,:dom, CAST(:geom AS jsonb)) "
                "ON CONFLICT (cd_setor) DO UPDATE SET populacao=:pop, "
                " domicilios=:dom, geometry=CAST(:geom AS jsonb)"
            ),
            {
                "cd": cd, "mun": CD_MUN, "nmun": _fix(gi(rec, "NM_MUN")),
                "dist": str(gi(rec, "CD_DIST") or ""), "ndist": _fix(gi(rec, "NM_DIST")),
                "subd": _fix(gi(rec, "NM_SUBDIST")), "bai": _fix(gi(rec, "NM_BAIRRO") or ""),
                "sit": _fix(gi(rec, "SITUACAO")),
                "area": (lambda a: float(str(a).replace(",", ".")) if a not in (None, "") else None)(gi(rec, "AREA_KM2")),
                "pop": pop, "dom": dom,
                "geom": json.dumps(sr.shape.__geo_interface__),
            },
        )
        n += 1
        if n % 100 == 0:
            db.commit()
    db.commit()

    chk = db.execute(
        text(
            "SELECT count(*) setores, sum(populacao) pop, sum(domicilios) dom, "
            "count(distinct nm_dist) distritos, "
            "count(distinct nm_bairro) FILTER (WHERE nm_bairro<>'') bairros "
            "FROM census_geo WHERE cd_mun=:m"
        ),
        {"m": CD_MUN},
    ).first()
    print(f"inseridos {n} setores. conferência: setores={chk[0]} pop={chk[1]} "
          f"dom={chk[2]} distritos={chk[3]} bairros={chk[4]}")


if __name__ == "__main__":
    main()
