"""
Voto de 2o turno tem de ser GUARDADO, nao descartado.

O importador tinha um `if _turno == 1` na acumulacao: toda linha de 2o turno
era jogada fora. Na pratica, no dia do segundo turno o sistema importaria o
arquivo do TSE e nao guardaria voto nenhum.

Nao virou coluna em tse_vote_results de proposito — a chave la e
(candidato, municipio), sem turno, e somar os dois faria Lula 2022 aparecer com
117 milhoes em vez de 57.
"""
from app.models.tse import Candidate, Election, Municipality, Party, VoteResult
from app.models.tse.runoff_vote import TseRunoffVote


def _cenario(db):
    """Mesmo candidato com votos nos DOIS turnos, como no arquivo do TSE."""
    e1 = Election(tse_code=111, year=2026, round=1, name="Geral 2026 1T")
    e2 = Election(tse_code=112, year=2026, round=2, name="Geral 2026 2T")
    partido = Party(number=13, abbreviation="ABC", name="Partido ABC")
    db.add_all([e1, e2, partido])
    db.flush()

    m = Municipality(tse_code=40001, name="Capital", state="ZZ")
    db.add(m)
    db.flush()

    cand = Candidate(
        election_id=e2.id, party_id=partido.id, sq_candidato=400001,
        number=13, name="FINALISTA", urn_name="FINALISTA", office_code=3,
        office_name="GOVERNADOR", state="ZZ", result_status="ELEITO",
        total_votes=0,
    )
    db.add(cand)
    db.flush()
    return m, cand


def test_os_dois_turnos_convivem_sem_somar(db_session):
    """O ponto todo: 1o e 2o turno do MESMO candidato no MESMO municipio, sem
    um contaminar o outro."""
    m, cand = _cenario(db_session)

    db_session.add(VoteResult(candidate_id=cand.id, municipality_id=m.id,
                              votes=57_000))
    db_session.add(TseRunoffVote(candidate_id=cand.id, municipality_id=m.id,
                                 votes=60_000))
    db_session.commit()

    primeiro = db_session.query(VoteResult).filter_by(
        candidate_id=cand.id, municipality_id=m.id).one()
    segundo = db_session.query(TseRunoffVote).filter_by(
        candidate_id=cand.id, municipality_id=m.id).one()

    assert primeiro.votes == 57_000
    assert segundo.votes == 60_000
    # E o que as consultas antigas leem continua sendo so o 1o turno.
    assert db_session.query(VoteResult).filter_by(candidate_id=cand.id).count() == 1


def test_uma_linha_por_candidato_e_municipio(db_session):
    """A chave unica impede duplicata num re-import."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    m, cand = _cenario(db_session)
    db_session.add(TseRunoffVote(candidate_id=cand.id, municipality_id=m.id,
                                 votes=100))
    db_session.commit()

    db_session.add(TseRunoffVote(candidate_id=cand.id, municipality_id=m.id,
                                 votes=200))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# A cascata (ON DELETE CASCADE) e regra do BANCO, nao do nosso codigo: o SQLite
# da suite nao impoe chave estrangeira por padrao, entao um teste aqui mediria o
# motor, nao a aplicacao. Conferida direto no Postgres de producao.
