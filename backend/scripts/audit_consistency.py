"""Auditoria de consistência de dados — cruza features e totais."""
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.tse import Candidate, Election, Municipality, Party, VoteResult

db = SessionLocal()

print("=== CANDIDATOS POR ELEICAO ===")
for y in [2014, 2016, 2018, 2020, 2022, 2024]:
    eids = [e for (e,) in db.execute(select(Election.id).where(Election.year == y)).all()]
    nc = db.execute(
        select(func.count(func.distinct(Candidate.id))).where(Candidate.election_id.in_(eids))
    ).scalar()
    print(f"  {y}: {nc:,} candidatos")

print()
print("=== PRESIDENCIAL 2022 (deve bater com TSE real) ===")
reais = {"LULA": 57259504, "JAIR BOLSONARO": None, "SIMONE TEBET": 4915423,
         "CIRO GOMES": 3599287}
for n, real in reais.items():
    r = db.execute(
        select(Candidate.id, Candidate.urn_name)
        .join(Election, Candidate.election_id == Election.id)
        .where(Candidate.urn_name.ilike(n), Election.year == 2022,
               Candidate.office_name == "Presidente")
        .limit(1)
    ).first()
    if not r:
        print(f"  {n}: nao achou")
        continue
    s = int(db.execute(
        select(func.coalesce(func.sum(VoteResult.votes), 0)).where(VoteResult.candidate_id == r[0])
    ).scalar())
    nm = db.execute(
        select(func.count(func.distinct(VoteResult.municipality_id))).where(VoteResult.candidate_id == r[0])
    ).scalar()
    flag = "" if real is None else ("  OK" if s == real else f"  DIFF (real {real:,})")
    print(f"  {r[1]:<18} {s:>12,} votos · {nm:,} munis{flag}")

print()
print("=== TOTAIS GERAIS ===")
nc = db.execute(select(func.count(Candidate.id))).scalar()
nv = db.execute(select(func.count(VoteResult.id))).scalar()
nm = db.execute(select(func.count(Municipality.id))).scalar()
npy = db.execute(select(func.count(Party.id))).scalar()
print(f"  candidatos: {nc:,}")
print(f"  vote_results: {nv:,}")
print(f"  municipios: {nm:,}")
print(f"  partidos: {npy}")

print()
print("=== INTEGRIDADE ===")
# resultados com status preenchido
sem_status = db.execute(
    select(func.count(Candidate.id)).where(Candidate.result_status.is_(None))
).scalar()
print(f"  candidatos sem result_status: {sem_status:,} ({sem_status*100//nc}%)")
# duplicidade (candidate_id, municipality_id) em vote_results
dup = db.execute(
    select(func.count()).select_from(
        select(VoteResult.candidate_id, VoteResult.municipality_id)
        .group_by(VoteResult.candidate_id, VoteResult.municipality_id)
        .having(func.count() > 1).subquery()
    )
).scalar()
print(f"  vote_results duplicados (cand,muni): {dup}")
