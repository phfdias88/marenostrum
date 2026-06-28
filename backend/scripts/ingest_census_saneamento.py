"""
Saneamento por município (IBGE Censo 2022 — Agregados por Setores, arquivo
"Características do Domicílio Parte 2": água, esgoto, lixo).

Stream do zip (84MB) linha a linha (não carrega o CSV de ~452k setores em
memória — derruba o VPS). Soma os setores por município (setor[:7] = cd_mun).
'Adequado': água = rede geral (V00111); esgoto = rede + fossa ligada à rede
(V00309+V00310); lixo = coletado + caçamba (V00397+V00398).

Rodar: docker compose exec -T api sh -c 'PYTHONPATH=/app python /tmp/ingest_saneamento.py'
"""
import csv
import io
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionLocal

URL = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/"
    "Agregados_por_setores_caracteristicas_domicilio2_BR_20250417.zip"
)
ZIP_PATH = Path("/tmp/saneamento.zip")

AGUA = [f"V{n:05d}" for n in range(111, 119)]   # V00111..V00118
ESG = [f"V{n:05d}" for n in range(309, 316)]     # V00309..V00315
LIX = [f"V{n:05d}" for n in range(397, 403)]     # V00397..V00402


def _num(s):
    s = (s or "").strip().strip('"')
    if not s or s.upper() == "X":  # X = sigilo
        return None
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def main() -> None:
    if not ZIP_PATH.exists():
        print(f"baixando saneamento (~84MB): {URL}")
        req = urllib.request.Request(URL, headers={"User-Agent": "marenostrum/1.0"})
        with urllib.request.urlopen(req, timeout=600) as r, open(ZIP_PATH, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    acc = defaultdict(lambda: dict(ar=0, at=0, ea=0, et=0, lc=0, lt=0))

    zf = zipfile.ZipFile(ZIP_PATH)
    name = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
    print(f"streaming {name}")
    with zf.open(name) as raw:
        txt = io.TextIOWrapper(raw, encoding="latin-1", newline="")
        rdr = csv.reader(txt, delimiter=";")
        hdr = [h.strip().strip('"').upper() for h in next(rdr)]
        idx = {h: i for i, h in enumerate(hdr)}
        i_set = idx.get("SETOR", idx.get("CD_SETOR"))
        ia = [idx[c] for c in AGUA]
        ie = [idx[c] for c in ESG]
        il = [idx[c] for c in LIX]
        rows = 0
        for row in rdr:
            rows += 1
            cd7 = row[i_set].strip('"')[:7]
            a = [_num(row[i]) for i in ia]
            e = [_num(row[i]) for i in ie]
            x = [_num(row[i]) for i in il]
            d = acc[cd7]
            d["ar"] += a[0] or 0
            d["at"] += sum(v for v in a if v)
            d["ea"] += (e[0] or 0) + (e[1] or 0)
            d["et"] += sum(v for v in e if v)
            d["lc"] += (x[0] or 0) + (x[1] or 0)
            d["lt"] += sum(v for v in x if v)
            if rows % 100000 == 0:
                print(f"  {rows} setores...")
    print(f"setores lidos: {rows} | municípios: {len(acc)}")

    db = SessionLocal()
    try:
        muns = [r[0] for r in db.execute(
            text("SELECT cd_mun FROM census_geo WHERE level='municipio'")
        ).all()]
        upd = text(
            "UPDATE census_geo SET dom_agua_rede=:ar, dom_agua_total=:at, "
            "dom_esgoto_adequado=:ea, dom_esgoto_total=:et, "
            "dom_lixo_coletado=:lc, dom_lixo_total=:lt "
            "WHERE level='municipio' AND cd_mun=:cd"
        )
        n = 0
        for cd in muns:
            d = acc.get(cd)
            if not d:
                continue
            db.execute(upd, {"cd": cd, "ar": d["ar"], "at": d["at"],
                             "ea": d["ea"], "et": d["et"], "lc": d["lc"], "lt": d["lt"]})
            n += 1
        db.commit()
        print(f"municípios atualizados com saneamento: {n}")
        sample = db.execute(text(
            "SELECT nm_mun, round(100.0*dom_esgoto_adequado/NULLIF(dom_esgoto_total,0),1) "
            "FROM census_geo WHERE level='municipio' AND dom_esgoto_total>0 "
            "ORDER BY nm_mun LIMIT 5"
        )).all()
        print("amostra % esgoto adequado:")
        for s in sample:
            print(f"  {s[0]}: {s[1]}%")
    finally:
        db.close()


if __name__ == "__main__":
    main()
