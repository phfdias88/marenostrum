"""
Ingestão CadÚnico + Bolsa Família por município (MDS/SAGI — MI Social).

API pública estilo Solr (sem auth), todos os municípios numa request — mesmo
estilo do ingest_census_renda.py com o SIDRA. Granularidade município × mês.

Endpoint: https://aplicacoes.mds.gov.br/sagi/servicos/misocial
  fq=tipo_s:mes_mu  (1 linha por município-mês)
  fq=anomes_s:AAAAMM
  fl=...  (aliases dos campos)

Gotcha: codigo_ibge do MDS tem 6 dígitos (ex 330455); census_geo.cd_mun tem 7
(3304557, com dígito verificador). Casamos por LEFT(cd_mun,6)=codigo_ibge usando
os municípios que já existem no census_geo (evita reimplementar o DV do IBGE).
Por isso só popula os municípios que têm censo (hoje: RJ — igual à renda).

Rodar dentro do container api:
  docker compose exec -T api python -m scripts.ingest_mds_social
  (opcional fixar o mês: MDS_ANOMES=202605 docker compose exec ...)
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import date

from sqlalchemy import text

from app.core.database import SessionLocal

BASE = "https://aplicacoes.mds.gov.br/sagi/servicos/misocial"
FL = (
    "ibge:codigo_ibge,anomes:anomes_s,"
    "cad_fam:cadun_qtd_familias_cadastradas_i,"
    "cad_pes:cadun_qtd_pessoas_cadastradas_i,"
    "pbf_fam:qtd_familias_beneficiarias_bolsa_familia_i,"
    "pbf_pes:qtd_pessoas_beneficiarias_bolsa_familia_i,"
    "pbf_val:valor_repassado_bolsa_familia_s"
)


def _num(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "null", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(v):
    f = _num(v)
    return int(f) if f is not None else None


def fetch(anomes: str, ibge: str | None = None) -> list[dict]:
    fqs = ["tipo_s:mes_mu", f"anomes_s:{anomes}"]
    if ibge:
        fqs.append(f"codigo_ibge:{ibge}")
    qs = urllib.parse.urlencode(
        {
            "q": "*", "fq": fqs, "wt": "json", "omitHeader": "true",
            "rows": 20000, "fl": FL, "sort": "codigo_ibge asc",
        },
        doseq=True,
    )
    req = urllib.request.Request(f"{BASE}?{qs}", headers={"User-Agent": "marenostrum/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("response", {}).get("docs", [])


def latest_anomes() -> str | None:
    """Volta mês a mês (a partir do atual) até achar um com CadÚnico preenchido.
    Usa o Rio (330455) como sonda — meses futuros vêm vazios na API."""
    y, m = date.today().year, date.today().month
    for _ in range(24):
        am = f"{y:04d}{m:02d}"
        docs = fetch(am, ibge="330455")
        if docs and _int(docs[0].get("cad_fam")):
            return am
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return None


def main() -> None:
    am = os.environ.get("MDS_ANOMES") or latest_anomes()
    if not am:
        print("ERRO: não achei mês com dado do CadÚnico")
        return
    print(f"baixando MDS MI Social anomes={am}")
    docs = fetch(am)
    by6 = {str(d.get("ibge")): d for d in docs if d.get("ibge")}
    print(f"municípios no MDS: {len(by6)}")

    db = SessionLocal()
    try:
        muns = [r[0] for r in db.execute(
            text("SELECT cd_mun FROM census_geo WHERE level='municipio'")
        ).all()]
        print(f"municípios no census_geo: {len(muns)}")

        upsert = text(
            "INSERT INTO mds_social_municipio "
            "(cd_mun, anomes, cadunico_familias, cadunico_pessoas, "
            " pbf_familias, pbf_pessoas, pbf_valor) "
            "VALUES (:cd,:am,:cf,:cp,:pf,:pp,:pv) "
            "ON CONFLICT (cd_mun, anomes) DO UPDATE SET "
            " cadunico_familias=excluded.cadunico_familias, "
            " cadunico_pessoas=excluded.cadunico_pessoas, "
            " pbf_familias=excluded.pbf_familias, "
            " pbf_pessoas=excluded.pbf_pessoas, "
            " pbf_valor=excluded.pbf_valor"
        )
        n = 0
        for cd7 in muns:
            d = by6.get(cd7[:6])
            if not d:
                continue
            db.execute(upsert, {
                "cd": cd7, "am": am,
                "cf": _int(d.get("cad_fam")), "cp": _int(d.get("cad_pes")),
                "pf": _int(d.get("pbf_fam")), "pp": _int(d.get("pbf_pes")),
                "pv": _num(d.get("pbf_val")),
            })
            n += 1
        db.commit()
        print(f"municípios gravados: {n}")

        sample = db.execute(text(
            "SELECT m.cd_mun, g.nm_mun, m.cadunico_familias, m.pbf_familias "
            "FROM mds_social_municipio m "
            "JOIN census_geo g ON g.cd_mun=m.cd_mun AND g.level='municipio' "
            "WHERE m.anomes=:am ORDER BY m.cadunico_familias DESC NULLS LAST LIMIT 5"
        ), {"am": am}).all()
        print("top 5 CadÚnico (famílias):")
        for s in sample:
            print(f"  {s[1]}: CadÚnico {s[2]} fam | Bolsa Família {s[3]} fam")
    finally:
        db.close()


if __name__ == "__main__":
    main()
