"""
Contato do CRM politico (eleitor, lider, apoiador, doador, etc).
Sempre vinculado a um tenant.
"""
import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, String
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

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    type: Mapped[ContactType] = mapped_column(
        SAEnum(ContactType, name="contact_type"),
        nullable=False,
        default=ContactType.VOTER,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    __table_args__ = (
        Index("ix_contacts_tenant_id_id", "tenant_id", "id"),
        Index("ix_contacts_tenant_name", "tenant_id", "full_name"),
    )
