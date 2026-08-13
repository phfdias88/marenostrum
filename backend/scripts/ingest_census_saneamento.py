"""
Saneamento (IBGE Censo 2022 — Agregados por Setores, arquivo "Características do
Domicílio Parte 2": água, esgoto, lixo).

Grava em DOIS níveis do census_geo:
  - level='setor'      → cada setor recebe suas contagens (o painel do bairro
                         agrega os setores e mostra o % por bairro; é o dado
                         de valor — saneamento varia MUITO dentro da cidade).
  - level='municipio'  → soma por município (indicador municipal, retrocompat).

Stream do zip (~84MB) linha a linha (não carrega o CSV de ~452k setores em
memória — derrubaria o VPS 1vCPU). Só acumula/atualiza os setores que EXISTEM
em census_geo (pré-carrega o conjunto de cd_setor), então a memória fica limitada
aos ~205k setores já ingeridos, não aos 452k do país.

'Adequado': água = rede geral (V00111); esgoto = rede + fossa ligada à rede
(V00309+V00310); lixo = coletado + caçamba (V00397+V00398). Totais = soma das
categorias da variável (denominador do %).

Rodar (scripts/ NÃO vai na imagem — cp + PYTHONPATH):
  docker compose cp backend/scripts/ingest_census_saneamento.py api:/tmp/ing_san.py
  docker compose exec -T api sh -c 'PYTHONPATH=/app python /tmp/ing_san.py'
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

SETOR_UPDATE = (
    "UPDATE census_geo AS c SET "
    "  dom_agua_rede=d.ar::int, dom_agua_total=d.at::int, "
    "  dom_esgoto_adequado=d.ea::int, dom_esgoto_total=d.et::int, "
    "  dom_lixo_coletado=d.lc::int, dom_lixo_total=d.lt::int "
    "FROM (VALUES {rows}) AS d(cd, ar, at, ea, et, lc, lt) "
    "WHERE c.level='setor' AND c.cd_setor = d.cd::text"
)


def _num(s):
    s = (s or "").strip().strip('"')
    if not s or s.upper() == "X":  # X = sigilo
        return None
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def _row_vals(a, e, x):
    """(agua_rede, agua_total, esgoto_adeq, esgoto_total, lixo_colet, lixo_total)."""
    return (
        a[0] or 0,
        sum(v for v in a if v),
        (e[0] or 0) + (e[1] or 0),
        sum(v for v in e if v),
        (x[0] or 0) + (x[1] or 0),
        sum(v for v in x if v),
    )


def _flush_setor(db, batch):
    if not batch:
        return 0
    placeholders = []
    params = {}
    for i, (cd, ar, at, ea, et, lc, lt) in enumerate(batch):
        placeholders.append(
            f"(:cd{i},:ar{i},:at{i},:ea{i},:et{i},:lc{i},:lt{i})"
        )
        params.update({
            f"cd{i}": cd, f"ar{i}": ar, f"at{i}": at, f"ea{i}": ea,
            f"et{i}": et, f"lc{i}": lc, f"lt{i}": lt,
        })
    db.execute(text(SETOR_UPDATE.format(rows=",".join(placeholders))), params)
    return len(batch)


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

    db = SessionLocal()
    try:
        # conjunto de setores que existem em census_geo (limita a memória e as
        # atualizações — só toca no que já ingerimos).
        setor_set = {
            r[0] for r in db.execute(
                text("SELECT cd_setor FROM census_geo WHERE level='setor'")
            ).all()
        }
        print(f"setores em census_geo: {len(setor_set)}")

        acc_muni = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
        setor_batch = []
        BATCH = 500
        setor_written = 0

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
                cd15 = row[i_set].strip('"')
                a = [_num(row[i]) for i in ia]
                e = [_num(row[i]) for i in ie]
                x = [_num(row[i]) for i in il]
                ar, at, ea, et, lc, lt = _row_vals(a, e, x)

                # município (retrocompat do indicador municipal)
                m = acc_muni[cd15[:7]]
                m[0] += ar; m[1] += at; m[2] += ea
                m[3] += et; m[4] += lc; m[5] += lt

                # setor (só os que temos)
                if cd15 in setor_set:
                    setor_batch.append((cd15, ar, at, ea, et, lc, lt))
                    if len(setor_batch) >= BATCH:
                        setor_written += _flush_setor(db, setor_batch)
                        setor_batch = []
                        db.commit()

                if rows % 100000 == 0:
                    print(f"  {rows} setores lidos... ({setor_written} gravados)")

        setor_written += _flush_setor(db, setor_batch)
        db.commit()
        print(f"setores lidos: {rows} | setores gravados: {setor_written} "
              f"| municípios: {len(acc_muni)}")

        # nível município
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
            d = acc_muni.get(cd)
            if not d:
                continue
            db.execute(upd, {"cd": cd, "ar": d[0], "at": d[1], "ea": d[2],
                             "et": d[3], "lc": d[4], "lt": d[5]})
            n += 1
        db.commit()
        print(f"municípios atualizados: {n}")

        sample = db.execute(text(
            "SELECT nm_bairro, "
            "  round(100.0*sum(dom_esgoto_adequado)/NULLIF(sum(dom_esgoto_total),0),1) esg, "
            "  round(100.0*sum(dom_agua_rede)/NULLIF(sum(dom_agua_total),0),1) agua "
            "FROM census_geo WHERE level='setor' AND cd_mun='3304557' "
            "  AND nm_bairro IS NOT NULL "
            "GROUP BY nm_bairro HAVING sum(dom_esgoto_total)>0 "
            "ORDER BY esg ASC LIMIT 6"
        )).all()
        print("amostra Rio — bairros com menor % esgoto adequado:")
        for s in sample:
            print(f"  {s[0]}: esgoto {s[1]}% · água {s[2]}%")
    finally:
        db.close()


if __name__ == "__main__":
    main()
