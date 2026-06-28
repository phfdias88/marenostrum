"""
IDHM municipal (Atlas Brasil/PNUD-IPEA-FJP) — IDHM + subíndices educação,
longevidade e renda. Via mirror público do Base dos Dados (CSV.gz no GCS, sem
auth). Última versão municipal completa = Censo 2010 (não há IDHM Censo 2022).

Rodar: docker compose exec -T api sh -c 'PYTHONPATH=/app python /tmp/ingest_idhm.py'
"""
import csv
import gzip
import io
import urllib.request

from sqlalchemy import text

from app.core.database import SessionLocal

URL = "https://storage.googleapis.com/basedosdados-public/one-click-download/mundo_onu_adh/municipio/municipio.csv.gz"
ANO = "2010"


def _num(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def main() -> None:
    print(f"baixando IDHM: {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": "marenostrum/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        blob = r.read()
    text_io = io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(blob)), encoding="utf-8")
    rdr = csv.DictReader(text_io)

    idhm: dict[str, dict] = {}
    for row in rdr:
        if str(row.get("ano")).strip() != ANO:
            continue
        cd = str(row.get("id_municipio") or "").strip()
        if len(cd) != 7:
            continue
        idhm[cd] = {
            "i": _num(row.get("idhm")),
            "e": _num(row.get("idhm_e")),
            "l": _num(row.get("idhm_l")),
            "r": _num(row.get("idhm_r")),
        }
    print(f"municípios com IDHM {ANO}: {len(idhm)}")

    db = SessionLocal()
    try:
        muns = [r[0] for r in db.execute(
            text("SELECT cd_mun FROM census_geo WHERE level='municipio'")
        ).all()]
        upd = text(
            "UPDATE census_geo SET idhm=:i, idhm_educacao=:e, "
            "idhm_longevidade=:l, idhm_renda=:r "
            "WHERE level='municipio' AND cd_mun=:cd"
        )
        n = 0
        for cd in muns:
            v = idhm.get(cd)
            if not v:
                continue
            db.execute(upd, {"cd": cd, "i": v["i"], "e": v["e"], "l": v["l"], "r": v["r"]})
            n += 1
        db.commit()
        print(f"municípios atualizados com IDHM: {n}")
        sample = db.execute(text(
            "SELECT nm_mun, idhm FROM census_geo WHERE level='municipio' "
            "AND idhm IS NOT NULL ORDER BY idhm DESC LIMIT 5"
        )).all()
        print("top 5 IDHM:")
        for s in sample:
            print(f"  {s[0]}: {s[1]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
