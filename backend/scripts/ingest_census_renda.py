"""
Ingestão da RENDA domiciliar por município (IBGE Censo 2022) via API SIDRA.

Tabela 3168, variáveis:
  847 = rendimento nominal MÉDIO   mensal dos domicílios particulares permanentes
  848 = rendimento nominal MEDIANO mensal dos domicílios particulares permanentes
Nível n6 (município), todos os municípios, último período. Sem filtro de
classificação → o SIDRA devolve o "Total" (1 linha por município × variável).

Casa por cd_mun (D1C, 7 dígitos IBGE) e dá UPDATE só nas linhas
level='municipio' do census_geo. Municípios sem censo na base não são afetados.

Rodar dentro do container api:
  docker compose exec -T api python -m scripts.ingest_census_renda
"""
import urllib.request

from sqlalchemy import text

from app.core.database import SessionLocal

SIDRA_URL = "https://apisidra.ibge.gov.br/values/t/3168/n6/all/v/847,848/p/last"


def _num(s):
    s = (s or "").strip()
    # SIDRA: "-" sem ocorrência, ".."/"..." não aplicável, "X" sigilo.
    if not s or s in ("-", "..", "...", "X"):
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def fetch_sidra() -> dict[str, dict]:
    """cd_mun -> {'media': float|None, 'mediana': float|None}."""
    import json

    req = urllib.request.Request(SIDRA_URL, headers={"User-Agent": "marenostrum/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # 1º elemento é o cabeçalho (códigos -> rótulos); pula.
    out: dict[str, dict] = {}
    for row in data[1:]:
        cd = (row.get("D1C") or "").strip()          # Município (código)
        var = (row.get("D2C") or "").strip()         # Variável (código)
        val = _num(row.get("V"))
        if not cd or len(cd) != 7:
            continue
        slot = out.setdefault(cd, {"media": None, "mediana": None})
        if var == "847":
            slot["media"] = val
        elif var == "848":
            slot["mediana"] = val
    return out


def main() -> None:
    print(f"baixando SIDRA: {SIDRA_URL}")
    renda = fetch_sidra()
    print(f"municípios com renda no SIDRA: {len(renda)}")

    db = SessionLocal()
    try:
        # Só os municípios que existem no census_geo (level='municipio').
        muns = [r[0] for r in db.execute(
            text("SELECT cd_mun FROM census_geo WHERE level='municipio'")
        ).all()]
        print(f"municípios no census_geo: {len(muns)}")

        upd = text(
            "UPDATE census_geo SET renda_media_domiciliar=:me, "
            "renda_mediana_domiciliar=:md "
            "WHERE level='municipio' AND cd_mun=:cd"
        )
        n = 0
        for cd in muns:
            r = renda.get(cd)
            if not r:
                continue
            db.execute(upd, {"cd": cd, "me": r["media"], "md": r["mediana"]})
            n += 1
        db.commit()
        print(f"municípios atualizados com renda: {n}")

        # Amostra de verificação.
        sample = db.execute(text(
            "SELECT nm_mun, renda_media_domiciliar, renda_mediana_domiciliar "
            "FROM census_geo WHERE level='municipio' "
            "AND renda_media_domiciliar IS NOT NULL ORDER BY renda_media_domiciliar DESC LIMIT 5"
        )).all()
        print("top 5 renda média:")
        for s in sample:
            print(f"  {s[0]}: média R$ {s[1]} | mediana R$ {s[2]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
