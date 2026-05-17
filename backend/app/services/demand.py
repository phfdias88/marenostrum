"""
Service de Demands.

Regras de negocio:
- Toda demanda nasce de UM contato ATIVO do tenant. Se contato nao existe
  (ou foi soft-deletado), POST falha com 404.
- Update partial; contact_id e' imutavel (nao move demanda entre contatos).
- Hard delete (sem soft) — quem quer manter use status='cancelada'.
"""
from uuid import UUID

import structlog

from app.core.errors import NotFoundError
from app.core.tenant_context import TenantContext
from app.models.demand import Demand, DemandStatus
from app.repositories.contact import ContactRepository
from app.repositories.demand import DemandRepository
from app.schemas.demand import DemandCreate, DemandUpdate

log = structlog.get_logger("marenostrum.services.demand")


class DemandService:
    def __init__(self, ctx: TenantContext) -> None:
        self._ctx = ctx
        self._repo = DemandRepository(ctx.db)
        self._contacts = ContactRepository(ctx.db)

    # ---------------------------------------------------------------- Create

    def create_demand(self, payload: DemandCreate) -> Demand:
        # Valida que o contato e' do nosso tenant e esta ATIVO.
        # Sem isso, atacante poderia adivinhar contact_id de outro tenant.
        contact = self._contacts.get_by_id(
            tenant_id=self._ctx.tenant_id,
            contact_id=payload.contact_id,
        )
        if contact is None:
            raise NotFoundError("Contato nao encontrado.")

        demand = self._repo.create(
            tenant_id=self._ctx.tenant_id,
            data=payload.model_dump(),
        )
        self._ctx.db.commit()

        log.info(
            "demand_created",
            tenant_id=str(self._ctx.tenant_id),
            user_id=str(self._ctx.user_id),
            demand_id=str(demand.id),
            contact_id=str(demand.contact_id),
        )
        return demand

    # ------------------------------------------------------------------ Read

    def get_demand(self, demand_id: UUID) -> Demand:
        demand = self._repo.get_by_id(
            tenant_id=self._ctx.tenant_id,
            demand_id=demand_id,
        )
        if demand is None:
            raise NotFoundError("Demanda nao encontrada.")
        return demand

    def list_demands(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: DemandStatus | None = None,
        contact_id: UUID | None = None,
    ) -> tuple[list[Demand], int]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        # Se filtra por contact_id, valida que o contato e' do nosso tenant
        # ANTES de listar — evita enumeration pelo timing.
        if contact_id is not None:
            # include_inactive=True: demandas de contato soft-deleted
            # devem continuar listaveis pelo perfil (historico).
            contact = self._contacts.get_by_id(
                tenant_id=self._ctx.tenant_id,
                contact_id=contact_id,
                include_inactive=True,
            )
            if contact is None:
                raise NotFoundError("Contato nao encontrado.")

        items = self._repo.list_paginated(
            tenant_id=self._ctx.tenant_id,
            limit=limit, offset=offset,
            status=status, contact_id=contact_id,
        )
        total = self._repo.count(
            tenant_id=self._ctx.tenant_id,
            status=status, contact_id=contact_id,
        )
        return items, total

    # ---------------------------------------------------------------- Update

    def update_demand(self, demand_id: UUID, payload: DemandUpdate) -> Demand:
        data = payload.model_dump(exclude_unset=True)
        updated = self._repo.update(
            tenant_id=self._ctx.tenant_id,
            demand_id=demand_id,
            data=data,
        )
        if updated is None:
            raise NotFoundError("Demanda nao encontrada.")
        self._ctx.db.commit()
        log.info(
            "demand_updated",
            tenant_id=str(self._ctx.tenant_id),
            demand_id=str(demand_id),
            fields=list(data.keys()),
        )
        return updated

    # ---------------------------------------------------------------- Delete

    def delete_demand(self, demand_id: UUID) -> None:
        ok = self._repo.delete(
            tenant_id=self._ctx.tenant_id,
            demand_id=demand_id,
        )
        if not ok:
            raise NotFoundError("Demanda nao encontrada.")
        self._ctx.db.commit()
        log.info(
            "demand_deleted",
            tenant_id=str(self._ctx.tenant_id),
            demand_id=str(demand_id),
        )
