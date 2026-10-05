"""Repository de usuarios (somente queries usadas pelo modulo auth por enquanto)."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, user: User) -> User:
        """Persiste alterações no usuário (usado pelo trial no 1º login)."""
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)
        return user

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

    def list_active_by_email(self, *, email: str) -> list[tuple[User, Tenant]]:
        """Todos os usuários ATIVOS com este e-mail, em tenants ATIVOS.

        Usado no login sem `tenant_slug`: o mesmo e-mail pode existir em mais de
        uma campanha (ex.: dono da própria conta e coordenador em outra), então
        o Service resolve qual pela senha — e pede escolha se houver empate.
        """
        stmt = (
            select(User, Tenant)
            .join(Tenant, User.tenant_id == Tenant.id)
            .where(
                User.email == email,
                User.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
        )
        return [(row[0], row[1]) for row in self._db.execute(stmt).all()]

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
