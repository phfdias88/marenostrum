"""
Ingestão da RENDA DOS RESPONSÁVEIS por SETOR CENSITÁRIO (Censo 2022).

Complementa o ingest municipal (ingest_census_renda_responsavel.py): a renda é
o indicador mais pedido pra microssegmentar discurso, e antes SUMIA ao dar zoom
no município (só existia em level='municipio'). Este script preenche por setor:
  V06001 = nº de responsáveis (peso da média ponderada na agregação por bairro)
  V06004 = rendimento nominal MÉDIO mensal dos responsáveis
  V06006 = rendimento nominal MEDIANO mensal

Grava em census_geo (level='setor'): renda_media_resp_2022,
renda_mediana_resp_2022, responsaveis_2022 (colunas da migration 055). Só toca
os ~200k setores já presentes no census_geo (o arquivo BR tem ~458k).
O frontend agrega por bairro/distrito via média ponderada por `responsaveis`
(lib/censusAggregate.ts já pré-registrou esse peso).

Rodar DENTRO do container (a imagem agora copia scripts/):
  docker compose exec -T -e PYTHONPATH=/app api python scripts/ingest_census_renda_setor.py
Depois: bump CENSUS_V (frontend + warmup.py) + purge do cache mn_census.
"""
import csv
import io
import urllib.request
import zipfile

from sqlalchemy import text

from app.core.database import SessionLocal

# Data no nome do arquivo (o IBGE versiona por data) — mesma família do arquivo
# municipal verificado em jul/2026; ajuste a data se o FTP renomear.
ZIP_URL = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"
    "Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip"
)


def _num(s):
    s = (s or "").strip()
    if not s or s in ("-", "..", "...", "X"):
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def main() -> None:
    print(f"baixando IBGE: {ZIP_URL}", flush=True)
    req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "marenostrum/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read()
    print(f"zip: {len(raw) / 1e6:.1f} MB", flush=True)

    db = SessionLocal()
    try:
        known = {
            r[0]
            for r in db.execute(
                text("SELECT cd_setor FROM census_geo WHERE level='setor'")
            ).all()
        }
        print(f"setores no census_geo: {len(known)}", flush=True)

        upd = text(
            "UPDATE census_geo SET renda_media_resp_2022=:me, "
            "renda_mediana_resp_2022=:md, responsaveis_2022=:re "
            "WHERE cd_setor=:cd"
        )
        n = rows = 0
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_name = next(n_ for n_ in zf.namelist() if n_.lower().endswith(".csv"))
            with zf.open(csv_name) as fh:
                reader = csv.DictReader(
                    io.TextIOWrapper(fh, encoding="latin-1"), delimiter=";"
                )
                for row in reader:
                    rows += 1
                    cd = (row.get("CD_SETOR") or row.get("CD_setor") or "").strip()
                    if cd not in known:
                        continue
                    me = _num(row.get("V06004"))
                    md = _num(row.get("V06006"))
                    re_ = _num(row.get("V06001"))
                    if me is None and md is None:
                        continue
                    db.execute(upd, {
                        "cd": cd, "me": me, "md": md,
                        "re": int(re_) if re_ is not None else None,
                    })
                    n += 1
                    if n % 5000 == 0:
                        db.commit()
                        print(f"  ... {n} setores", flush=True)
        db.commit()
        print(f"linhas no arquivo: {rows} | setores atualizados: {n}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
