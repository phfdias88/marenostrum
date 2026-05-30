"""
Contato do CRM politico (eleitor, lider, apoiador, doador, etc).
Sempre vinculado a um tenant.

Fase 3 adiciona campos de georreferenciamento (lat/lng) e aniversario.
Lat/lng como Float (double precision) — suficiente sem PostGIS no MVP.
"""
import enum
from datetime import date

from sqlalchemy import Date, Enum as SAEnum
from sqlalchemy import Float, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class ContactType(str, enum.Enum):
    VOTER = "voter"           # eleitor cadastrado
    LEADER = "leader"         # lideranca comunitaria
    SUPPORTER = "supporter"   # apoiador ativo
    DONOR = "donor"           # doador de campanha
    OTHER = "other"


class Contact(Base, TenantMixin, TimestampMixin):
    __tablename__ = "contacts"

    # Identidade
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Endereco
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Geocoordenadas (opcionais — preenchidas via Nominatim/Google futuramente)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Pessoais
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Tags livres pra segmentacao (ex: "doador-2024", "lideranca-bairro-x").
    # JSONB array de strings. Indice GIN com jsonb_path_ops em migration 020.
    # Default em DB e' '[]'::jsonb — Python sempre ve' lista nunca None.
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    # Classificacao
    type: Mapped[ContactType] = mapped_column(
        # Ver nota em user.py sobre values_callable — sem isso PG rejeita.
        SAEnum(
            ContactType,
            name="contact_type",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=ContactType.VOTER,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Soft delete: DELETE da API vira UPDATE is_active=False.
    # Mantem integridade referencial (interactions, demands continuam validos).
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    __table_args__ = (
        # Indice composto para queries multi-tenant (sempre filtram por tenant_id)
        Index("ix_contacts_tenant_id_id", "tenant_id", "id"),
        Index("ix_contacts_tenant_name", "tenant_id", "full_name"),
        # Telefone unico DENTRO de um tenant (regra de negocio Fase 3)
        UniqueConstraint("tenant_id", "phone", name="uq_contacts_tenant_phone"),
    )
