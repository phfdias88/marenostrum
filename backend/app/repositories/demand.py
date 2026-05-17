"""
Repository de Demands.

REGRA: tenant_id em TODA query.
Usa joinedload(Demand.contact) pra evitar N+1 ao serializar DemandRead.
"""
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, joinedload

from app.models.demand import Demand, DemandStatus


class DemandRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # -------------------------------------------------------------- Create

    def create(self, *, tenant_id: UUID, data: dict[str, Any]) -> Demand:
        data.pop("tenant_id", None)
        demand = Demand(tenant_id=tenant_id, **data)
        self._db.add(demand)
        self._db.flush()
        # Re-carrega com contact JOIN pra responder a UI sem extra-query
        return self.get_by_id(tenant_id=tenant_id, demand_id=demand.id)  # type: ignore[return-value]

    # ---------------------------------------------------------------- Read

    def get_by_id(
        self,
        *,
        tenant_id: UUID,
        demand_id: UUID,
    ) -> Demand | None:
        stmt = (
            select(Demand)
            .options(joinedload(Demand.contact))
            .where(
                Demand.id == demand_id,
                Demand.tenant_id == tenant_id,
            )
        )
        return self._db.execute(stmt).unique().scalar_one_or_none()

    def count(
        self,
        *,
        tenant_id: UUID,
        status: DemandStatus | None = None,
        contact_id: UUID | None = None,
    ) -> int:
        stmt = select(func.count(Demand.id)).where(Demand.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(Demand.status == status)
        if contact_id is not None:
            stmt = stmt.where(Demand.contact_id == contact_id)
        return int(self._db.execute(stmt).scalar_one())

    def list_paginated(
        self,
        *,
        tenant_id: UUID,
        limit: int,
        offset: int,
        status: DemandStatus | None = None,
        contact_id: UUID | None = None,
    ) -> list[Demand]:
        """
        Lista demandas com contato JA carregado (joinedload).
        Mais recentes primeiro.
        """
        stmt = (
            select(Demand)
            .options(joinedload(Demand.contact))
            .where(Demand.tenant_id == tenant_id)
        )
        if status is not None:
            stmt = stmt.where(Demand.status == status)
        if contact_id is not None:
            stmt = stmt.where(Demand.contact_id == contact_id)
        stmt = (
            stmt.order_by(Demand.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.execute(stmt).unique().scalars().all())

    # -------------------------------------------------------------- Update

    def update(
        self,
        *,
        tenant_id: UUID,
        demand_id: UUID,
        data: dict[str, Any],
    ) -> Demand | None:
        # contact_id e' imutavel via update (decisao de design — schema
        # tambem nao aceita)
        data.pop("tenant_id", None)
        data.pop("contact_id", None)
        data.pop("id", None)
        if not data:
            return self.get_by_id(tenant_id=tenant_id, demand_id=demand_id)

        stmt = (
            update(Demand)
            .where(
                Demand.id == demand_id,
                Demand.tenant_id == tenant_id,
            )
            .values(**data)
        )
        result = self._db.execute(stmt)
        if result.rowcount == 0:
            return None
        # Re-carrega com joinedload
        return self.get_by_id(tenant_id=tenant_id, demand_id=demand_id)

    # -------------------------------------------------------------- Delete

    def delete(self, *, tenant_id: UUID, demand_id: UUID) -> bool:
        """Hard delete — demanda errada ao cadastrar e' removida.
        Quem quer manter historico usa status='cancelada'."""
        stmt = delete(Demand).where(
            Demand.id == demand_id,
            Demand.tenant_id == tenant_id,
        )
        return (self._db.execute(stmt).rowcount or 0) > 0
