"""
Interaction: registro imutavel de qualquer evento externo que toca o CRM
(webhook do BotConversa, SMS recebido, log de campanha disparada, etc).

DECISOES:
- contact_id e' OPCIONAL — webhook pode chegar de telefone que ainda nao
  esta no CRM. Salvamos a interacao "orfa" (contact_id=NULL) + phone
  preservado pra relink em batch futuro.
- phone duplicado em coluna propria mesmo havendo contact_id:
  (a) preserva o numero exato que chegou no payload (formatos divergem),
  (b) permite agregacao sem JOIN,
  (c) sobrevive se contato for deletado (FK ON DELETE SET NULL).
- payload_data como JSON cross-DB (sa.JSON), nao JSONB. PG aceita JSON
  com fallback pra serializar. Pra prod com queries pesadas em payload,
  migrar pra JSONB depois (ALTER TYPE sem perda).
- external_event_id indexed mas NAO unique (ainda). Idempotencia real
  fica pra fase futura quando soubermos o formato dos IDs do BotConversa.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Interaction(Base, TenantMixin, TimestampMixin):
    __tablename__ = "interactions"

    # Vinculo opcional ao contato (NULL = interacao orfa, vai ser relinkada
    # quando o contato real for cadastrado no CRM)
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Telefone exato como veio no payload (preserva formatacao)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Classificacao do evento (string livre — provedores variam):
    # 'mensagem_recebida', 'mensagem_enviada', 'fluxo_concluido', etc
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Canal: 'whatsapp', 'sms', 'email', 'instagram'...
    channel: Mapped[str] = mapped_column(
        String(40), nullable=False, default="whatsapp"
    )

    # ID do evento no sistema externo (BotConversa, Zenvia, etc).
    # Indexado pra busca rapida; sem UNIQUE (idempotencia em fase futura).
    external_event_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )

    # Payload bruto. Tipo JSON e' cross-DB (PG: json, SQLite: TEXT validado).
    # Em PG considere ALTER TYPE pra JSONB se precisar de operadores ->> e GIN.
    payload_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Timestamp recebido — separado de created_at por clareza semantica:
    # received_at = quando o evento chegou no nosso servidor.
    # created_at (TimestampMixin) = quando o registro foi gravado (geralmente igual).
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Compostos pra queries tipicas (sempre filtram por tenant_id)
        Index("ix_interactions_tenant_id_id", "tenant_id", "id"),
        Index("ix_interactions_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_interactions_tenant_phone", "tenant_id", "phone"),
        Index(
            "ix_interactions_tenant_received_at",
            "tenant_id",
            "received_at",
        ),
    )
