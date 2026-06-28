"""
Pré-computa o sumário por eleição (candidatos, votos, municípios) nas colunas
tse_elections.stats_* (migration 047), pra /elections/{id}/stats ser instantâneo.

O count(distinct município) varre vote_results e é lento em eleições municipais
grandes (~72s p/ 505k candidatos) — por isso roda aqui (background), 1x.

Rodar: docker compose exec -d api sh -c 'PYTHONPATH=/app python /tmp/pop_estats.py'
"""
from sqlalchemy import func, select, text
from app.core.database import SessionLocal
from app.models.tse import Candidate, Election, VoteResult


def main() -> None:
    with SessionLocal() as db:
        eids = list(db.execute(
            select(Election.id).where(Election.stats_candidates.is_(None))
        ).scalars())
    print(f"eleições a popular: {len(eids)}", flush=True)
    for i, eid in enumerate(eids, 1):
        with SessionLocal() as db:
            c = int(db.execute(select(func.count(Candidate.id)).where(Candidate.election_id == eid)).scalar_one())
            v = int(db.execute(select(func.coalesce(func.sum(Candidate.total_votes), 0)).where(Candidate.election_id == eid)).scalar_one())
            m = int(db.execute(
                select(func.count(func.distinct(VoteResult.municipality_id)))
                .select_from(VoteResult).join(Candidate, Candidate.id == VoteResult.candidate_id)
                .where(Candidate.election_id == eid)
            ).scalar_one())
            db.execute(text(
                "UPDATE tse_elections SET stats_candidates=:c, stats_total_votes=:v, "
                "stats_municipalities=:m WHERE id=:id"
            ), {"c": c, "v": v, "m": m, "id": eid})
            db.commit()
        if i % 20 == 0 or i == len(eids):
            print(f"  {i}/{len(eids)}", flush=True)
    print("ESTATS DONE", flush=True)


if __name__ == "__main__":
    main()
