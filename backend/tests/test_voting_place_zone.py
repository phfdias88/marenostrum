"""
A zona eleitoral faz parte da identidade do local de votacao.

No TSE o NR_LOCAL_VOTACAO so e unico DENTRO da zona. Sem a zona na chave, o
"local 12" da 1a zona e o "local 12" da 5a viravam a mesma linha e o bairro de
um deles levava os votos de todos — foi assim que o Rio ficou com 163 locais
para uma cidade de mais de 1.400, um deles com 129.241 eleitores.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.tse import Municipality
from app.models.tse.voting_place import TseVotingPlace


def _muni(db):
    m = Municipality(tse_code=60001, name="Cidade Zonas", state="ZZ")
    db.add(m)
    db.commit()
    return m


def test_mesmo_numero_em_zonas_diferentes_convive(db_session):
    """O caso que estava quebrado: dois locais reais, mesmo numero, zonas
    diferentes, bairros diferentes. Tem de virar DUAS linhas."""
    m = _muni(db_session)
    db_session.add_all([
        TseVotingPlace(year=2024, zone=1, local_code=12, municipality_id=m.id,
                       name="ESCOLA DO CENTRO", neighborhood="CENTRO",
                       electors_total=2000),
        TseVotingPlace(year=2024, zone=5, local_code=12, municipality_id=m.id,
                       name="ESCOLA DA PRAIA", neighborhood="COPACABANA",
                       electors_total=1800),
    ])
    db_session.commit()

    locais = db_session.query(TseVotingPlace).filter_by(municipality_id=m.id).all()
    assert len(locais) == 2
    assert {l.neighborhood for l in locais} == {"CENTRO", "COPACABANA"}


def test_mesmo_numero_na_mesma_zona_continua_barrado(db_session):
    """A protecao antiga nao pode ter sumido: dentro da MESMA zona o numero
    continua unico."""
    m = _muni(db_session)
    db_session.add(
        TseVotingPlace(year=2024, zone=1, local_code=12, municipality_id=m.id,
                       name="ESCOLA A", neighborhood="CENTRO", electors_total=100)
    )
    db_session.commit()

    db_session.add(
        TseVotingPlace(year=2024, zone=1, local_code=12, municipality_id=m.id,
                       name="ESCOLA B", neighborhood="OUTRO", electors_total=100)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_mesma_zona_e_numero_em_anos_diferentes_convive(db_session):
    """Locais mudam entre pleitos: o ano segue na chave."""
    m = _muni(db_session)
    db_session.add_all([
        TseVotingPlace(year=2020, zone=1, local_code=12, municipality_id=m.id,
                       name="ESCOLA 2020", neighborhood="CENTRO", electors_total=100),
        TseVotingPlace(year=2024, zone=1, local_code=12, municipality_id=m.id,
                       name="ESCOLA 2024", neighborhood="CENTRO", electors_total=100),
    ])
    db_session.commit()
    assert db_session.query(TseVotingPlace).filter_by(municipality_id=m.id).count() == 2
