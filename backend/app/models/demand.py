"""
Demand = pedido/demanda da populacao para o gabinete.

Modelo central de mandato (campanha eleita): "fulano pediu X dia Y, status Z".
Diferencial de SaaS politico vs CRM generico.
"""
import enum
from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin
from app.models.contact import Contact


class DemandStatus(str, enum.Enum):
    OPEN = "aberta"
    IN_PROGRESS = "em_andamento"
    RESOLVED = "resolvida"
    CANCELLED = "cancelada"


class Demand(Base, TenantMixin, TimestampMixin):
    __tablename__ = "demands"

    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[DemandStatus] = mapped_column(
        SAEnum(DemandStatus, name="demand_status"),
        nullable=False,
        default=DemandStatus.OPEN,
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)

    # Obrigatorio: toda demanda nasce de alguem.
    # ON DELETE RESTRICT — nao deixa apagar contato com demandas pendentes
    # (contato e' soft-deleted no DELETE da API; essa proteção e' "cinto e
    # suspensorio" pro caso de hard-delete administrativo direto no DB).
    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Relationship pra carregar contato em JOIN (joinedload no repo).
    # lazy="raise" impede lazy loading acidental (N+1).
    contact: Mapped[Contact] = relationship("Contact", lazy="raise")

    __table_args__ = (
        Index("ix_demands_tenant_id_id", "tenant_id", "id"),
        Index("ix_demands_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_demands_tenant_status", "tenant_id", "status"),
        Index("ix_demands_tenant_created_at", "tenant_id", "created_at"),
    )
