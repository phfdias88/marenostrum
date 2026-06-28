"""
Import LEVE de candidatos históricos (anos pré-2014) para TRAJETÓRIA.

Cria Election + Party + Candidate com total_votes agregado, MAS NÃO grava
tse_vote_results (o detalhe por município é o que pesa — 5GB+). Assim a
trajetória eleitoral (ano/cargo/partido/votos/resultado) funciona para anos
antigos a custo mínimo de disco (~candidatos apenas).

Fonte: votacao_candidato_munzona_<ano>.zip (arquivo _BRASIL). Mesmo formato do
importer principal — confirmado p/ 2002–2012.

CPF fica NULL aqui; rodar depois o backfill nome→CPF único (liga Lula 2002/2006
ao CPF da candidatura 2022). total_votes = soma QT_VOTOS_NOMINAIS do 1º turno;
result_status pega o 2º turno quando houver.

Rodar (anos via env, default gerais):
  HIST_YEARS=2002,2006,2010 docker compose exec -T api sh -c 'PYTHONPATH=/app python /tmp/ingest_hist.py'
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import insert, select

from app.core.database import SessionLocal
from app.models.tse import Candidate, Election, Party
from app.utils.tse_sync import TSE_BASE_URL, _i, _s, download_zip, iter_csv_rows

YEARS = [int(y) for y in os.environ.get("HIST_YEARS", "2002,2006,2010").split(",")]
CHUNK = 5000

# SQ_CANDIDATO antigo (≤2012) só é único por (ano, UF) — NÃO globalmente, então
# colide com o índice único ix_tse_candidates_sq. Geramos um SQ SINTÉTICO único
# = ano*1e13 + cod_uf*1e11 + sq_bruto. (sq antigo é pequeno; cabe em BigInteger.
# Fica muito acima dos SQ modernos ~2.5e11, sem colisão.) O sq não é usado em
# nada downstream pros anos antigos (trajetória casa por cpf/nome).
UF_NUM = {uf: i + 1 for i, uf in enumerate([
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO", "ZZ", "BR",
])}


def _syn_sq(year: int, uf: str, raw_sq: int, office_code: int) -> int:
    # Presidente (cargo 1) é NACIONAL: aparece 1 linha por UF no munzona com o
    # MESMO sq → dedup SEM UF (slot uf=0), senão viram 27 candidatos. Demais
    # cargos são por UF (sq repete entre UFs) → inclui UF.
    uf_slot = 0 if office_code == 1 else UF_NUM.get(uf, 30)
    return year * 10**13 + uf_slot * 10**11 + (raw_sq % 10**11)


def ingest_year(db, year: int) -> None:
    url = f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_{year}.zip"
    zip_path = Path(f"/tmp/munzona_{year}.zip")
    if not zip_path.exists():
        print(f"  baixando {url}")
        download_zip(url, zip_path, max_mb=900)

    elections_by_tse = {e.tse_code: e.id for e in db.execute(select(Election)).scalars()}
    parties_by_number = {p.number: p.id for p in db.execute(select(Party)).scalars()}
    year_eids = list(db.execute(select(Election.id).where(Election.year == year)).scalars())
    cands_by_sq = {}
    if year_eids:
        cands_by_sq = {
            c.sq_candidato: c.id for c in db.execute(
                select(Candidate).where(Candidate.election_id.in_(year_eids))
            ).scalars()
        }

    elections_buf, parties_buf, cand_buf = [], [], []
    votes_by_sq: dict[int, int] = {}
    runoff: dict[int, str] = {}
    now = datetime.now(timezone.utc)
    rows = 0

    for _csv, row in iter_csv_rows(zip_path, name_contains="_BRASIL"):
        rows += 1
        ec = _i(row.get("CD_ELEICAO"))
        if ec and ec not in elections_by_tse:
            eid = uuid4(); elections_by_tse[ec] = eid
            elections_buf.append({
                "id": eid, "tse_code": ec, "year": _i(row.get("ANO_ELEICAO")),
                "round": _i(row.get("NR_TURNO")) or 1,
                "name": _s(row.get("DS_ELEICAO"), 180),
                "type_name": _s(row.get("NM_TIPO_ELEICAO"), 80),
                "created_at": now, "updated_at": now,
            })
        pn = _i(row.get("NR_PARTIDO"))
        if pn and pn not in parties_by_number:
            pid = uuid4(); parties_by_number[pn] = pid
            parties_buf.append({
                "id": pid, "number": pn, "abbreviation": _s(row.get("SG_PARTIDO"), 20),
                "name": _s(row.get("NM_PARTIDO"), 180), "created_at": now, "updated_at": now,
            })
        raw_sq = _i(row.get("SQ_CANDIDATO"))
        uf = _s(row.get("SG_UF"), 2).upper()
        office = _i(row.get("CD_CARGO"))
        sq = _syn_sq(_i(row.get("ANO_ELEICAO")) or year, uf, raw_sq, office) if raw_sq else 0
        turno = _i(row.get("NR_TURNO")) or 1
        if sq and turno == 1:
            votes_by_sq[sq] = votes_by_sq.get(sq, 0) + _i(row.get("QT_VOTOS_NOMINAIS"))
        if sq and turno == 2:
            st = _s(row.get("DS_SIT_TOT_TURNO"), 40) or None
            if st:
                runoff[sq] = st
        if sq and sq not in cands_by_sq and pn and ec:
            cid = uuid4(); cands_by_sq[sq] = cid
            cand_buf.append({
                "id": cid, "sq_candidato": sq, "election_id": elections_by_tse[ec],
                "number": _i(row.get("NR_CANDIDATO")), "name": _s(row.get("NM_CANDIDATO"), 180),
                "urn_name": _s(row.get("NM_URNA_CANDIDATO"), 180),
                "party_id": parties_by_number[pn], "office_code": _i(row.get("CD_CARGO")),
                "office_name": _s(row.get("DS_CARGO"), 40), "state": _s(row.get("SG_UF"), 2).upper(),
                "situation": _s(row.get("DS_SITUACAO_CANDIDATURA"), 40),
                "result_status": _s(row.get("DS_SIT_TOT_TURNO"), 40) or None,
                "_sq": sq,
                "created_at": now, "updated_at": now,
            })
        if rows % 500000 == 0:
            print(f"    {year}: {rows} linhas, {len(cand_buf)} cands novos")

    # total_votes + status final de 2º turno
    for c in cand_buf:
        sq = c.pop("_sq")
        c["total_votes"] = votes_by_sq.get(sq, 0)
        if sq in runoff:
            c["result_status"] = runoff[sq]

    # elections_buf/parties_buf só contêm itens NÃO presentes no cache (já no DB)
    # → insert simples é seguro, sem risco de conflito.
    if elections_buf:
        db.execute(insert(Election), elections_buf)
    if parties_buf:
        db.execute(insert(Party), parties_buf)
    db.commit()
    for i in range(0, len(cand_buf), CHUNK):
        db.execute(insert(Candidate), cand_buf[i:i + CHUNK])
        db.commit()
    print(f"  {year}: {rows} linhas → {len(cand_buf)} candidatos, {len(elections_buf)} eleições")


def main() -> None:
    print(f"anos: {YEARS}")
    for y in YEARS:
        with SessionLocal() as db:
            try:
                ingest_year(db, y)
            except Exception as e:  # noqa: BLE001
                import traceback
                print(f"FAIL {y}: {e}"); traceback.print_exc()
    print("ALL DONE")


if __name__ == "__main__":
    main()
