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
