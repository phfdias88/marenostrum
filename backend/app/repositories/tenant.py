"""Repository de tenants (queries usadas por webhook + admin)."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant


class TenantRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_active(self, *, tenant_id: UUID) -> Tenant | None:
        """Retorna tenant SOMENTE se ativo. Usado pra validar webhook."""
        stmt = select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.is_active.is_(True),
        )
        return self._db.execute(stmt).scalar_one_or_none()
