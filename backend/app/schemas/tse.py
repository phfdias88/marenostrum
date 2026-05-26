"""Schemas Pydantic pros endpoints TSE."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.tse import SyncJobStatus


class ElectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tse_code: int
    year: int
    round: int
    name: str
    type_name: str | None


class PartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: int
    abbreviation: str
    name: str


class MunicipalityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tse_code: int
    name: str
    state: str
    latitude: float | None = None
    longitude: float | None = None


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: int
    name: str
    urn_name: str
    office_code: int
    office_name: str
    state: str
    situation: str | None
    # Resultado da eleicao: ELEITO, ELEITO POR QP/MÉDIA, NÃO ELEITO,
    # SUPLENTE, 2º TURNO, etc. None se ainda nao backfilled.
    result_status: str | None = None
    # Enriquecimento (so preenchido no detalhe): patrimonio + redes sociais
    assets_total: float | None = None
    social_links: list[str] | None = None
    # Financas de campanha (prestacao de contas)
    revenue_total: float | None = None
    expense_total: float | None = None
    party: PartyRead
    election: ElectionRead


class VoteResultByMunicipality(BaseModel):
    """Resultado de UM candidato em UM município (pra montar tabela)."""
    municipality: MunicipalityRead
    votes: int


class CandidateResultsResponse(BaseModel):
    """GET /candidates/{id}/results — votos do candidato por município."""
    candidate: CandidateRead
    results: list[VoteResultByMunicipality]
    total_votes: int
    municipalities_with_votes: int


class TopCandidateInMunicipality(BaseModel):
    """Linha da tabela 'top candidatos no municipio X'."""
    candidate: CandidateRead
    votes: int


class MunicipalityResultsResponse(BaseModel):
    """GET /municipalities/{id}/top-candidates — top votados num municipio."""
    municipality: MunicipalityRead
    results: list[TopCandidateInMunicipality]
    total_results: int
    # Soma de TODOS os votos nominais do cargo no municipio (denominador
    # pra calcular % de cada candidato). 0 se nao houver filtro de cargo.
    total_votes: int = 0
    office_code: int | None = None
    office_name: str | None = None


class CandidateByNeighborhoodItem(BaseModel):
    """Linha de votos por bairro: nome + total + locais agregados + centroide."""
    neighborhood: str
    votes: int
    places_count: int
    electors_total: int
    # Centroide aprox dos locais (media simples)
    avg_lat: float | None
    avg_lng: float | None


class CandidateByNeighborhoodResponse(BaseModel):
    candidate: CandidateRead
    municipality: MunicipalityRead | None  # filtrado por municipio especifico
    items: list[CandidateByNeighborhoodItem]
    total_votes: int
    total_neighborhoods: int


class ElectionStatsResponse(BaseModel):
    """GET /elections/{id}/stats — sumario de uma eleicao."""
    election: ElectionRead
    candidates_count: int
    municipalities_count: int
    total_votes: int


class PartyPerformanceItem(BaseModel):
    """Desempenho de um partido: votos + eleitos + candidatos."""
    party: PartyRead
    total_votes: int
    elected_count: int
    candidates_count: int


class WinnerMapPoint(BaseModel):
    """Municipio + partido/candidato vencedor (pra mapa colorido)."""
    municipality_id: UUID
    name: str
    state: str
    lat: float
    lng: float
    party_number: int
    party_abbreviation: str
    winner_name: str
    votes: int


class WinnersMapResponse(BaseModel):
    year: int
    office_code: int
    points: list[WinnerMapPoint]


class RankedCandidate(BaseModel):
    """Linha do ranking nacional: candidato + total de votos."""
    candidate: CandidateRead
    total_votes: int


class TopCandidatesResponse(BaseModel):
    year: int
    office_code: int | None
    office_name: str | None
    state: str | None
    items: list[RankedCandidate]


class PartyPerformanceResponse(BaseModel):
    """GET /stats/party-performance — ranking de partidos por votos/eleitos."""
    year: int
    office_code: int | None
    office_name: str | None
    state: str | None
    items: list[PartyPerformanceItem]
    total_votes: int
    total_elected: int


class SyncJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    dataset: str
    year: int
    status: SyncJobStatus
    started_at: datetime | None
    completed_at: datetime | None
    rows_processed: int
    rows_total: int | None
    candidates_imported: int
    parties_imported: int
    municipalities_imported: int
    vote_results_imported: int
    error_message: str | None
    created_at: datetime


class SyncJobCreated(BaseModel):
    job_id: UUID = Field(..., description="Use em GET /tse/sync/{id} pra acompanhar progresso")
    dataset: str
    status: SyncJobStatus
