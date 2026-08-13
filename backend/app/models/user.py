"""
Usuario do sistema (membro da equipe de um candidato).
Sempre vinculado a um tenant.
"""
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, Index, String, UniqueConstraint
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
    # TITULAR da assinatura (quem comprou/paga a plataforma). Setado APENAS
    # pelo provisionamento do billing (webhook Asaas) ou pelo seed. Convidados
    # do painel de equipe SEMPRE nascem False — mesmo promovidos a owner
    # depois (role = permissão; esta flag = titularidade da conta).
    is_account_owner: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Super-acesso da consultoria Mare Nostrum: vê a auditoria de TODAS as
    # campanhas (cross-tenant). Setado só direto no banco (sem endpoint, anti-
    # escalonamento). Default false.
    is_superadmin: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Feature-flag: libera o módulo de Dados Censitários (IBGE) no menu do
    # usuário. Controlado pelo owner em Configurações > Equipe.
    census_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Acesso por área, configurável pelo owner por usuário (Coordenador/Equipe).
    # Default TRUE — mantém o acesso amplo que já existia; o owner desliga o que
    # quiser por pessoa. O owner sempre tem tudo (não é restringido por flag).
    analytics_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)  # Análises (TSE)
    panel_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)      # Painel
    map_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)        # Mapa da Campanha
    demands_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)    # Demandas
    agenda_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)     # Agenda

    # ------------------------------------------------ Acesso temporário (trial)
    # Conta de teste/demonstração com tempo de uso limitado. O relógio NÃO conta
    # da criação: só começa no PRIMEIRO login real (first_login_at), e a partir
    # daí corre de forma absoluta até expires_at.
    #   - usage_limit_hours: horas permitidas (ex: 2.5 = 2h30). NULL/0 = ilimitado.
    #   - first_login_at: carimbo do 1º login (NULL até logar pela 1ª vez).
    #   - expires_at: first_login_at + usage_limit_hours (materializado no 1º login).
    # O JWT emitido nunca vive além de expires_at (cap no login e no refresh).
    usage_limit_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Quando o subclass define __table_args__, ele substitui o do mixin.
    # Aqui combinamos: indice composto + unicidade do email por tenant.
    __table_args__ = (
        Index("ix_users_tenant_id_id", "tenant_id", "id"),
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
