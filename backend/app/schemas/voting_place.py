"""Schemas Pydantic para VotingPlace (locais de votação)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VotingPlaceBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=180)
    address: str | None = Field(None, max_length=255)
    neighborhood: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    votes: int = Field(0, ge=0)
    total_voters: int | None = Field(None, ge=0)
    election_year: int | None = Field(None, ge=1900, le=2100)
    tse_code: str | None = Field(None, max_length=40)
    notes: str | None = None


class VotingPlaceRead(VotingPlaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class HeatmapPoint(BaseModel):
    """Ponto único do heatmap: [lat, lng, intensity_normalized 0-1]."""
    lat: float
    lng: float
    intensity: float = Field(..., ge=0, le=1, description="0 a 1, normalizado por max")
    votes: int  # raw votes pra tooltip
    name: str   # nome do local pra hover


class HeatmapResponse(BaseModel):
    """Resposta do GET /voting-places/heatmap."""
    points: list[HeatmapPoint]
    total_places: int
    total_votes: int
    max_votes: int  # usado pro normalize


class NeighborhoodStats(BaseModel):
    """Linha da agregacao /by-neighborhood: total de votos+locais por bairro."""
    neighborhood: str
    total_places: int
    total_votes: int
    total_voters: int | None
    # Centroide do bairro (media das coords dos locais) — pra centrar mapa
    avg_lat: float | None
    avg_lng: float | None


class NeighborhoodStatsResponse(BaseModel):
    items: list[NeighborhoodStats]
    total_neighborhoods: int
    total_votes: int


class VotingImportResult(BaseModel):
    imported: int
    skipped: int
    total_rows: int
    errors: list[dict[str, str]] = Field(default_factory=list)
