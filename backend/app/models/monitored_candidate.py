"""
Candidato monitorado pelo tenant: 'meu candidato' + 'adversarios'.

Diferenca de Favorito (TSE):
- Favorito = bookmark pessoal, sem semantica
- Monitored = papel definido (is_mine / adversario) + label custom + cor
- Permite agregar/comparar de forma persistente no dashboard
"""
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class MonitoredCandidate(Base, TenantMixin, TimestampMixin):
    __tablename__ = "monitored_candidates"

    candidate_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    # NULL = usa o nome real do TSE; preencher para apelido customizado
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_mine: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Cor em hex pra cards/grafico (#RRGGBB)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "candidate_id", name="uq_monitored_tenant_candidate"
        ),
        Index("ix_monitored_tenant_mine", "tenant_id", "is_mine"),
    )
