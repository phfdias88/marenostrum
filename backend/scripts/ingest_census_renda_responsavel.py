"""
Ingestão da RENDA DOS RESPONSÁVEIS em domicílios particulares permanentes
ocupados (Censo 2022), por município.

Fonte (grátis, download direto): IBGE — Agregados por Setores Censitários,
"Rendimento do Responsável". Arquivo municipal:
  V06004 = rendimento nominal MÉDIO mensal das pessoas responsáveis
  V06006 = rendimento nominal MEDIANO mensal
R$ nominais de 2022. CSV com sep ';', decimal vírgula, encoding latin-1.

Grava em census_geo.renda_media_resp_2022 / renda_mediana_resp_2022
(level='municipio', casa por cd_mun = CD_MUN de 7 dígitos). NÃO toca as colunas
de 2010 (renda_media_domiciliar), que são de outro conceito (renda do domicílio).

Rodar (scripts/ não é copiado pra imagem — usar cp + PYTHONPATH):
  docker compose cp backend/scripts/ingest_census_renda_responsavel.py api:/tmp/
  docker compose exec -T -e PYTHONPATH=/app api python /tmp/ingest_census_renda_responsavel.py
"""
import csv
import io
import urllib.request
import zipfile

from sqlalchemy import text

from app.core.database import SessionLocal

# Data no nome do arquivo (o IBGE versiona por data). Verificado em jul/2026.
ZIP_URL = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"
    "Agregados_por_municipios_renda_responsavel_BR_20260508_csv.zip"
)


def _num(s):
    s = (s or "").strip()
    if not s or s in ("-", "..", "...", "X"):
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def fetch() -> dict[str, dict]:
    print(f"baixando IBGE: {ZIP_URL}", flush=True)
    req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "marenostrum/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read()
    out: dict[str, dict] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(csv_name) as fh:
            reader = csv.DictReader(
                io.TextIOWrapper(fh, encoding="latin-1"), delimiter=";"
            )
            for row in reader:
                cd = (row.get("CD_MUN") or "").strip()
                if len(cd) != 7:
                    continue
                out[cd] = {
                    "media": _num(row.get("V06004")),
                    "mediana": _num(row.get("V06006")),
                }
    return out


def main() -> None:
    renda = fetch()
    print(f"municípios no arquivo IBGE: {len(renda)}", flush=True)
    db = SessionLocal()
    try:
        muns = [
            r[0]
            for r in db.execute(
                text("SELECT cd_mun FROM census_geo WHERE level='municipio'")
            ).all()
        ]
        upd = text(
            "UPDATE census_geo SET renda_media_resp_2022=:me, "
            "renda_mediana_resp_2022=:md WHERE level='municipio' AND cd_mun=:cd"
        )
        n = 0
        for cd in muns:
            r = renda.get(cd)
            if not r:
                continue
            db.execute(upd, {"cd": cd, "me": r["media"], "md": r["mediana"]})
            n += 1
        db.commit()
        print(f"municípios atualizados: {n}", flush=True)
        for s in db.execute(
            text(
                "SELECT nm_mun, renda_media_resp_2022, renda_mediana_resp_2022 "
                "FROM census_geo WHERE level='municipio' AND renda_media_resp_2022 IS NOT NULL "
                "ORDER BY renda_media_resp_2022 DESC LIMIT 5"
            )
        ).all():
            print(f"  {s[0]}: média R$ {s[1]} | mediana R$ {s[2]}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
