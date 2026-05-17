"""
Usuario do sistema (membro da equipe de um candidato).
Sempre vinculado a um tenant.
"""
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin
import enum


class UserRole(str, enum.Enum):
    OWNER = "owner"        # candidato / dono da conta
    MANAGER = "manager"    # coordenador de campanha
    STAFF = "staff"        # equipe operacional
    VOLUNTEER = "volunteer"


class User(Base, TenantMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.STAFF,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Quando o subclass define __table_args__, ele substitui o do mixin.
    # Aqui combinamos: indice composto + unicidade do email por tenant.
    __table_args__ = (
        Index("ix_users_tenant_id_id", "tenant_id", "id"),
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
