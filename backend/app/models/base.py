"""
Bases ORM compartilhadas.

Decisoes:
- `Base` declarativo unico para todos os models.
- `TimestampMixin` adiciona created_at/updated_at automaticamente.
- `TenantMixin` injeta `tenant_id` indexado e nao-nulo em qualquer entidade
  do dominio do cliente. Toda tabela "de negocio" DEVE herdar deste mixin.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Base declarativa do SQLAlchemy 2.x (typed)."""

    # PK padrao UUID v4 - melhor para multi-tenant (nao expoe contagem).
    # sa.Uuid (cross-DB): em Postgres usa UUID nativo, em SQLite/MySQL usa CHAR.
    # Migrations Alembic continuam usando postgresql.UUID (SQL especifico).
    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """
    Garante isolamento logico:
    - Coluna tenant_id obrigatoria, indexada, com FK para tenants.id.
    - Indice composto (tenant_id, id) acelera lookups filtrados por tenant.

    REGRA INVIOLAVEL: todo Repository DEVE adicionar `where(Model.tenant_id == ctx.tenant_id)`.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[UUID]:  # noqa: N805
        return mapped_column(
            Uuid(as_uuid=True),
            ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )

    @declared_attr.directive
    def __table_args__(cls):  # noqa: N805
        return (
            Index(f"ix_{cls.__tablename__}_tenant_id_id", "tenant_id", "id"),
        )
