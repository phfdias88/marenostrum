"""Repository de usuarios (somente queries usadas pelo modulo auth por enquanto)."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_email_and_tenant_slug(
        self,
        *,
        email: str,
        tenant_slug: str,
    ) -> User | None:
        """
        Busca usuario ativo de um tenant ativo. Join garante que ambos
        existam e estejam habilitados em uma unica query.
        """
        stmt = (
            select(User)
            .join(Tenant, User.tenant_id == Tenant.id)
            .where(
                User.email == email,
                Tenant.slug == tenant_slug,
                User.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_with_tenant(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
    ) -> tuple[User, Tenant] | None:
        """
        Carrega user + tenant em uma query so. Usado pelo endpoint /me.
        Filtra duplo (user_id E tenant_id) — garante que o tenant_id do JWT
        bate com o do registro, mesmo apos cache/desincronizacao.
        """
        stmt = (
            select(User, Tenant)
            .join(Tenant, User.tenant_id == Tenant.id)
            .where(
                User.id == user_id,
                User.tenant_id == tenant_id,
            )
        )
        row = self._db.execute(stmt).first()
        return (row[0], row[1]) if row else None
