"""
Ingestão de SEXO + FAIXA ETÁRIA (Censo 2022), por setor censitário.

Fonte: IBGE — Agregados por Setores Censitários, agregado "Demografia" (BR).
Sexo: V01007 (masculino), V01008 (feminino).
Faixa etária (totais ambos os sexos, 11 faixas de 5 anos): V01031..V01041.
Contagens por setor; sigilo vem como "X" (vira None). Encoding latin-1, sep ';'.

Só atualiza setores que JÁ existem em census_geo (o projeto ingeriu RJ/SP), então
casa por cd_setor e ignora o resto do país. A agregação pra município é SUM no
endpoint (mesmo padrão de raça/alfabetização).

Rodar (cp + PYTHONPATH — scripts/ não vai pra imagem):
  docker compose cp backend/scripts/ingest_census_demografia.py api:/tmp/
  docker compose exec -T -e PYTHONPATH=/app api python /tmp/ingest_census_demografia.py
"""
import csv
import io
import urllib.request
import zipfile

from sqlalchemy import text

from app.core.database import SessionLocal

ZIP_URL = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/"
    "Agregados_por_setores_demografia_BR.zip"
)

# coluna destino -> código IBGE (agregado demografia)
COLS = {
    "sexo_masculino": "V01007",
    "sexo_feminino": "V01008",
    "idade_0_4": "V01031",
    "idade_5_9": "V01032",
    "idade_10_14": "V01033",
    "idade_15_19": "V01034",
    "idade_20_24": "V01035",
    "idade_25_29": "V01036",
    "idade_30_39": "V01037",
    "idade_40_49": "V01038",
    "idade_50_59": "V01039",
    "idade_60_69": "V01040",
    "idade_70_mais": "V01041",
}


def _int(s):
    s = (s or "").strip()
    if not s or s in ("-", "..", "...", "X"):
        return None
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def main() -> None:
    db = SessionLocal()
    try:
        existing = {
            r[0]
            for r in db.execute(
                text(
                    "SELECT cd_setor FROM census_geo "
                    "WHERE level='setor' AND cd_setor IS NOT NULL"
                )
            ).all()
        }
        print(f"setores no census_geo: {len(existing)}", flush=True)
        if not existing:
            print("nenhum setor no census_geo — nada a fazer.", flush=True)
            return

        print(f"baixando IBGE: {ZIP_URL}", flush=True)
        req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "marenostrum/1.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read()

        set_clause = ", ".join(f"{c}=:{c}" for c in COLS)
        upd = text(
            f"UPDATE census_geo SET {set_clause} "
            "WHERE level='setor' AND cd_setor=:cd"
        )
        updates: list[dict] = []
        read = 0
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            with zf.open(name) as fh:
                reader = csv.DictReader(
                    io.TextIOWrapper(fh, encoding="latin-1"), delimiter=";"
                )
                for row in reader:
                    read += 1
                    cd = (row.get("CD_setor") or row.get("CD_SETOR") or "").strip()
                    if cd not in existing:
                        continue
                    params: dict = {"cd": cd}
                    for col, code in COLS.items():
                        params[col] = _int(row.get(code))
                    updates.append(params)
        print(f"linhas lidas: {read}, casaram: {len(updates)}", flush=True)

        for i in range(0, len(updates), 1000):
            db.execute(upd, updates[i : i + 1000])
            db.commit()
        print(f"setores atualizados: {len(updates)}", flush=True)

        chk = db.execute(
            text(
                "SELECT sum(sexo_masculino), sum(sexo_feminino), sum(populacao) "
                "FROM census_geo WHERE level='setor' AND sexo_masculino IS NOT NULL"
            )
        ).first()
        print(f"check: masc={chk[0]} + fem={chk[1]} ~ pop={chk[2]}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
