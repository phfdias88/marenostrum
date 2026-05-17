"""Repository de usuarios (somente queries usadas pelo modulo auth por enquanto)."""
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
