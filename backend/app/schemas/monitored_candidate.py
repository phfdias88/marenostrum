"""Schemas para a API de candidatos monitorados (meu / adversarios)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MonitoredCreate(BaseModel):
    candidate_id: UUID
    label: str | None = Field(None, max_length=80)
    is_mine: bool = False
    color: str | None = Field(None, max_length=16)
    notes: str | None = Field(None, max_length=1000)


class MonitoredUpdate(BaseModel):
    label: str | None = Field(None, max_length=80)
    is_mine: bool | None = None
    color: str | None = Field(None, max_length=16)
    notes: str | None = Field(None, max_length=1000)


class MonitoredCandidateRead(BaseModel):
    """
    Combina dados de MonitoredCandidate + candidato TSE (snapshot).

    Snapshot do TSE simplifica frontend (uma chamada — uma lista) e evita
    JOIN cliente. Caso candidato seja removido em resync, `candidate_found`
    vira False e o frontend mostra placeholder.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    label: str | None = None
    is_mine: bool
    color: str | None = None
    notes: str | None = None
    created_at: datetime

    # Snapshot do candidato TSE (None se candidato removido)
    candidate_found: bool = True
    candidate_name: str | None = None
    candidate_number: int | None = None
    candidate_party_abbr: str | None = None
    candidate_office_name: str | None = None
    candidate_state: str | None = None
    candidate_municipality_name: str | None = None
    candidate_total_votes: int | None = None
    candidate_was_elected: bool | None = None
