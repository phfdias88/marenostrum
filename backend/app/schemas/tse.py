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
