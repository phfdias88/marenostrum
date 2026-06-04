"""Schemas para a agenda parlamentar/campanha."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgendaBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=160)
    description: str | None = Field(None, max_length=2000)
    starts_at: datetime
    location_name: str | None = Field(None, max_length=160)
    address: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    category: str | None = Field(None, max_length=40)


class AgendaCreate(AgendaBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Visita ao bairro Centro",
                "starts_at": "2026-06-10T14:00:00-03:00",
                "location_name": "Praça da Matriz",
                "city": "Juiz de Fora",
                "state": "MG",
                "category": "visita",
            }
        }
    )


class AgendaUpdate(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=160)
    description: str | None = Field(None, max_length=2000)
    starts_at: datetime | None = None
    location_name: str | None = Field(None, max_length=160)
    address: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    category: str | None = Field(None, max_length=40)


class AgendaRead(AgendaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
