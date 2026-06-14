"""Validação de consistência de dados — roda no servidor (tem DB).

Cruza agregados internos e compara com números REAIS conhecidos do TSE
para garantir que "os dados batem".
"""
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.tse import Candidate, Election, MunicipalityElectorate, VoteResult

db = SessionLocal()
ok = 0
fail = 0


def check(name, cond, detail=""):
    global ok, fail
    status = "PASS" if cond else "FAIL"
    if cond:
        ok += 1
    else:
        fail += 1
    print(f"[{status}] {name} {detail}")


def votes_of(cid):
    return db.execute(
        select(func.coalesce(func.sum(VoteResult.votes), 0)).where(
            VoteResult.candidate_id == cid
        )
    ).scalar()


def find(urn, year, office, rnd=1):
    return db.execute(
        select(Candidate.id, Candidate.result_status)
        .join(Election, Candidate.election_id == Election.id)
        .where(
            Candidate.urn_name.ilike(urn),
            Election.year == year,
            Candidate.office_name == office,
            Election.round == rnd,
        )
    ).first()


# --- Contagens base
years = sorted({y for (y,) in db.execute(select(Election.year).distinct()).all()})
check("Eleições 2014–2024", years == [2014, 2016, 2018, 2020, 2022, 2024], str(years))

nelect = db.execute(select(func.count(MunicipalityElectorate.municipality_id))).scalar()
check("Eleitorado: 5569 municípios", nelect == 5569, str(nelect))

# --- Orfãos
orphan = db.execute(
    select(func.count())
    .select_from(VoteResult)
    .outerjoin(Candidate, Candidate.id == VoteResult.candidate_id)
    .where(Candidate.id.is_(None))
).scalar()
check("Sem vote_results órfãos", orphan == 0, f"órfãos={orphan}")

# --- Números REAIS conhecidos do TSE (validação externa)
eb = find("EDUARDO BOLSONARO", 2018, "Deputado Federal")
if eb:
    v = votes_of(eb[0])
    check("Eduardo Bolsonaro 2018 = 1.843.735 votos", v == 1843735, f"got={v:,}")
    check("Eduardo Bolsonaro 2018 = ELEITO", str(eb[1] or "").upper().startswith("ELEITO"), repr(eb[1]))

jb = find("JAIR BOLSONARO", 2018, "Presidente")
if jb:
    check("Jair Bolsonaro 2018 Presidente = ELEITO", str(jb[1] or "").upper().startswith("ELEITO"), repr(jb[1]))

lula = find("LULA", 2022, "Presidente", 1)
if lula:
    v = votes_of(lula[0])
    # Real 1º turno 2022: 57.259.504. Tolerância p/ cobertura de seções.
    check("Lula Pres 2022 1ºturno ~57.2M", 56_000_000 <= v <= 58_000_000, f"got={v:,}")

# --- Consistência cruzada: top candidato de uma eleição existe e soma > 0
top = db.execute(
    select(VoteResult.candidate_id, func.sum(VoteResult.votes).label("t"))
    .join(Candidate, Candidate.id == VoteResult.candidate_id)
    .join(Election, Election.id == Candidate.election_id)
    .where(Election.year == 2022, Candidate.office_name == "Deputado Federal")
    .group_by(VoteResult.candidate_id)
    .order_by(func.sum(VoteResult.votes).desc())
    .limit(1)
).first()
if top:
    check("Top dep. federal 2022 tem votos > 0", (top[1] or 0) > 0, f"={top[1]:,}")

print(f"=== {ok} PASS / {fail} FAIL ===")
