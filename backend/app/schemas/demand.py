"""Schemas Pydantic para Demand (demandas do gabinete)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.demand import DemandStatus


# --------------------------------------------------------- nested contact


class DemandContactSummary(BaseModel):
    """Resumo do contato aninhado em DemandRead (carregado via joinedload)."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    full_name: str


# ----------------------------------------------------------------- input


class DemandCreate(BaseModel):
    """POST /demands. contact_id obrigatorio (toda demanda nasce de alguem)."""
    contact_id: UUID
    title: str = Field(..., min_length=3, max_length=180)
    description: str = Field(..., min_length=1, max_length=10_000)
    category: str = Field(..., min_length=1, max_length=80)
    status: DemandStatus = DemandStatus.OPEN


class DemandUpdate(BaseModel):
    """PUT /demands/{id}: partial update. contact_id e' imutavel (use DELETE+POST)."""
    title: str | None = Field(None, min_length=3, max_length=180)
    description: str | None = Field(None, min_length=1, max_length=10_000)
    category: str | None = Field(None, min_length=1, max_length=80)
    status: DemandStatus | None = None


class DemandStatusUpdate(BaseModel):
    """PATCH atalho — usado pelo Dropdown rapido na DataTable."""
    status: DemandStatus


# ----------------------------------------------------------------- output


class DemandRead(BaseModel):
    """Leitura completa, com contato aninhado pra UI listar sem N+1 query."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact: DemandContactSummary
    title: str
    description: str
    status: DemandStatus
    category: str
    created_at: datetime
    updated_at: datetime
