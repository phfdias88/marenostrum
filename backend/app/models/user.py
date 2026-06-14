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
        # values_callable: instrui SA a usar os VALUES do enum ('owner') em vez
        # dos NAMES ('OWNER') — bate com os valores literais criados na
        # migration via postgresql.ENUM(...). Sem isso, INSERT falha em PG real
        # com "invalid input value for enum user_role: OWNER".
        SAEnum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=UserRole.STAFF,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Feature-flag: libera o módulo de Dados Censitários (IBGE) no menu do
    # usuário. Controlado pelo owner em Configurações > Equipe.
    census_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Quando o subclass define __table_args__, ele substitui o do mixin.
    # Aqui combinamos: indice composto + unicidade do email por tenant.
    __table_args__ = (
        Index("ix_users_tenant_id_id", "tenant_id", "id"),
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
