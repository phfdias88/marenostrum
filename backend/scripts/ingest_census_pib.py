"""
PIB municipal (IBGE PIB-Munic) via API SIDRA — tabela 5938, variável 37
(Produto Interno Bruto a preços correntes, em Mil Reais; ano mais recente=2023).

per capita = pib_total / populacao (população do Censo 2022 que já está no
census_geo) — evita baixar o xlsx do FTP. É a mesma lógica do IBGE (per capita
2022/2023 usa a população do Censo 2022).

Rodar: docker compose exec -T api sh -c 'PYTHONPATH=/app python /tmp/ingest_pib.py'
"""
import json
import urllib.request

from sqlalchemy import text

from app.core.database import SessionLocal

SIDRA_URL = "https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/last"


def _num(s):
    s = (s or "").strip()
    if not s or s in ("-", "..", "...", "X"):
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def main() -> None:
    print(f"baixando SIDRA PIB: {SIDRA_URL}")
    req = urllib.request.Request(SIDRA_URL, headers={"User-Agent": "marenostrum/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode("utf-8"))
    pib: dict[str, float] = {}
    for row in data[1:]:  # 1ª linha é cabeçalho
        cd = (row.get("D1C") or "").strip()
        v = _num(row.get("V"))
        if len(cd) == 7 and v is not None:
            pib[cd] = v * 1000.0  # Mil Reais -> Reais

    db = SessionLocal()
    try:
        muns = [r[0] for r in db.execute(
            text("SELECT cd_mun FROM census_geo WHERE level='municipio'")
        ).all()]
        upd = text(
            "UPDATE census_geo SET pib_total=:t, "
            "pib_per_capita = CASE WHEN populacao>0 THEN :t/populacao ELSE NULL END "
            "WHERE level='municipio' AND cd_mun=:cd"
        )
        n = 0
        for cd in muns:
            t = pib.get(cd)
            if t is None:
                continue
            db.execute(upd, {"cd": cd, "t": t})
            n += 1
        db.commit()
        print(f"municípios com PIB no SIDRA: {len(pib)} | atualizados: {n}")
        sample = db.execute(text(
            "SELECT nm_mun, round(pib_per_capita::numeric,0) FROM census_geo "
            "WHERE level='municipio' AND pib_per_capita IS NOT NULL "
            "ORDER BY pib_per_capita DESC LIMIT 5"
        )).all()
        print("top 5 PIB per capita:")
        for s in sample:
            print(f"  {s[0]}: R$ {s[1]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
