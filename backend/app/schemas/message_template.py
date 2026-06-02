"""Schemas para templates de mensagem (WhatsApp)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemplateBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    body: str = Field(..., min_length=2, max_length=2000)
    category: str | None = Field(None, max_length=40)


class TemplateCreate(TemplateBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Parabéns de aniversário",
                "body": "Olá {nome}! 🎉 Parabéns pelo seu aniversário! "
                "Muita saúde e alegria. Conte com a gente em {cidade}.",
                "category": "aniversário",
            }
        }
    )


class TemplateUpdate(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=120)
    body: str | None = Field(None, min_length=2, max_length=2000)
    category: str | None = Field(None, max_length=40)


class TemplateRead(TemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
