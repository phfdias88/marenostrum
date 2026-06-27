"""
Service de contatos: regras de negocio.

Controller -> Service -> Repository.
Service nao conhece HTTPException — levanta DomainError. Controller (camada
HTTP) traduz pra status via register_exception_handlers.

Geocoding: chamado em BackgroundTask do FastAPI quando o endereco mudou e
nao veio lat/lng explicito. Roda DEPOIS da resposta — UX nao espera Nominatim.
"""
from datetime import date as _date, timedelta
from uuid import UUID

import structlog
from fastapi import BackgroundTasks

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.tenant_context import TenantContext
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.repositories.contact import ContactRepository
from app.repositories.interaction import InteractionRepository
from app.services.audit import record_audit
from app.schemas.contact import (
    BirthdayContact,
    ContactCreate,
    ContactUpdate,
    ImportResult,
    ImportRowError,
    TagItem,
)
from app.utils.csv_import import parse_csv
from app.utils.geocoding import geocode_and_persist_contact

log = structlog.get_logger("marenostrum.services.contact")


# -------------------------------------------------------- helpers privados


def _needs_geocoding(contact: Contact) -> bool:
    """
    Decide se vale rodar geocoding. Criterio:
    - Nao temos lat/lng ainda
    - Temos pelo menos algum sinal de endereco (address OU neighborhood)
    """
    has_coords = contact.latitude is not None and contact.longitude is not None
    has_addr_signal = bool(contact.address or contact.neighborhood)
    return (not has_coords) and has_addr_signal


def _schedule_geocoding(
    tasks: BackgroundTasks | None,
    contact: Contact,
) -> None:
    """Agenda geocoding em background. No-op se tasks=None (chamadas internas)."""
    if tasks is None or not _needs_geocoding(contact):
        return
    tasks.add_task(
        geocode_and_persist_contact,
        contact_id=contact.id,
        tenant_id=contact.tenant_id,
        address=contact.address,
        neighborhood=contact.neighborhood,
        city=contact.city,
        state=contact.state,
    )


# -------------------------------------------------------------------- class


class ContactService:
    # Papéis com edição TOTAL — podem alterar/excluir qualquer contato do
    # tenant. Os demais (staff/"Comum", volunteer) só mexem no que cadastraram.
    _FULL_EDIT_ROLES = {"owner", "manager"}

    def __init__(self, ctx: TenantContext) -> None:
        self._ctx = ctx
        self._repo = ContactRepository(ctx.db)

    def _assert_can_edit(self, contact: Contact) -> None:
        """Regra "Comum edita só o que enviou": papéis sem edição total só
        podem alterar/excluir contatos que ELES mesmos cadastraram."""
        role = (self._ctx.role or "").lower()
        if role in self._FULL_EDIT_ROLES:
            return
        if (
            contact.created_by_user_id is not None
            and contact.created_by_user_id == self._ctx.user_id
        ):
            return
        raise ForbiddenError(
            "Você só pode editar ou excluir os contatos que você mesmo cadastrou."
        )

    # ---------------------------------------------------------------- Create

    def create_contact(
        self,
        payload: ContactCreate,
        background_tasks: BackgroundTasks | None = None,
    ) -> Contact:
        if payload.phone and self._repo.exists_by_phone(
            tenant_id=self._ctx.tenant_id,
            phone=payload.phone,
        ):
            raise ConflictError("Ja existe um contato com este telefone.")

        data = payload.model_dump(exclude_none=False)
        # Carimba quem cadastrou (liderança/membro) — pro owner filtrar depois.
        data["created_by_user_id"] = self._ctx.user_id
        data["created_by_name"] = self._ctx.user_name or None
        contact = self._repo.create(
            tenant_id=self._ctx.tenant_id,
            data=data,
        )
        record_audit(
            self._ctx,
            action="create",
            entity_type="contact",
            entity_id=contact.id,
            summary=f"Cadastrou contato {contact.full_name}",
        )
        self._ctx.db.commit()

        log.info(
            "contact_created",
            tenant_id=str(self._ctx.tenant_id),
            user_id=str(self._ctx.user_id),
            contact_id=str(contact.id),
        )

        _schedule_geocoding(background_tasks, contact)
        return contact

    # ------------------------------------------------------------------ Read

    def get_contact(self, contact_id: UUID) -> Contact:
        contact = self._repo.get_by_id(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
        )
        if contact is None:
            raise NotFoundError("Contato nao encontrado.")
        return contact

    def list_contacts(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        tag: str | None = None,
        created_by: UUID | None = None,
    ) -> tuple[list[Contact], int]:
        """Retorna (items, total) com filtro opcional por nome (ILIKE) + tag + autor."""
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        # Normaliza: string vazia/whitespace = sem filtro
        search = search.strip() if search else None
        if search == "":
            search = None
        tag = tag.strip().lower() if tag else None
        if tag == "":
            tag = None

        items = self._repo.list_paginated(
            tenant_id=self._ctx.tenant_id,
            limit=limit,
            offset=offset,
            search=search,
            tag=tag,
            created_by=created_by,
        )
        total = self._repo.count(
            tenant_id=self._ctx.tenant_id,
            search=search,
            tag=tag,
            created_by=created_by,
        )
        return items, total

    def list_creators(self) -> list[dict]:
        """Quem já cadastrou contato (id + nome) — alimenta o filtro 'cadastrado por'."""
        rows = self._repo.list_creators(tenant_id=self._ctx.tenant_id)
        return [{"id": str(uid), "name": name} for uid, name in rows]

    # ----------------------------------------------------- Tags & Birthdays

    def list_tag_summary(self) -> list[TagItem]:
        """Lista tags distintas no tenant + contagem de uso."""
        rows = self._repo.list_tag_summary(tenant_id=self._ctx.tenant_id)
        return [TagItem(tag=t, count=n) for (t, n) in rows]

    def list_birthdays(self, *, days_ahead: int = 0) -> list[BirthdayContact]:
        """
        Aniversariantes hoje (days_ahead=0) ou janela futura.
        Ex: days_ahead=6 = hoje + proximos 6 dias = semana.
        """
        # Usa data UTC; pra Brasil real UTC-3 ja' garante "hoje"
        # razoavel pro cidadao (corte e' a meia-noite UTC ~ 21h BR).
        ref = _date.today()
        rows = self._repo.list_birthdays(
            tenant_id=self._ctx.tenant_id,
            ref_date=ref,
            days_ahead=days_ahead,
        )
        out: list[BirthdayContact] = []
        for c, delta in rows:
            age = None
            if c.birth_date and c.birth_date.year > 1900:
                # idade que completa na proxima ocorrencia
                upcoming_year = (ref + timedelta(days=delta)).year
                age = upcoming_year - c.birth_date.year
            out.append(
                BirthdayContact(
                    id=c.id,
                    full_name=c.full_name,
                    phone=c.phone,
                    email=c.email,
                    birth_date=c.birth_date,  # type: ignore[arg-type]
                    days_until=delta,
                    age_turning=age,
                    tags=list(c.tags or []),
                )
            )
        return out

    def list_for_map(self) -> list[Contact]:
        return self._repo.list_with_coords(tenant_id=self._ctx.tenant_id)

    def map_aggregate(
        self,
        *,
        metric: str = "contacts",
        group_by: str = "neighborhood",
        state: str | None = None,
        city: str | None = None,
        neighborhood: str | None = None,
        type_: str | None = None,
        tag: str | None = None,
    ) -> list[dict]:
        """
        Agrega contatos (ou demandas) por bairro OU local de votação, com
        filtros — alimenta o Mapa da Campanha (bolhas + gráfico de barras).
        Posição da bolha = média das coordenadas dos contatos do grupo
        (avg ignora NULL no PG); grupos sem coordenada vêm com lat/lng None
        (aparecem só no gráfico, não no mapa).
        """
        import json as _json

        from sqlalchemy import text as _text

        grp_col = "voting_place" if group_by == "voting_place" else "neighborhood"
        sem = "local" if grp_col == "voting_place" else "bairro"
        key_expr = f"coalesce(nullif(trim(c.{grp_col}), ''), '(sem {sem})')"

        conds = ["c.tenant_id = :tid", "c.is_active = true"]
        params: dict = {"tid": str(self._ctx.tenant_id)}
        if state:
            conds.append("c.state = :state")
            params["state"] = state.upper()
        if city:
            conds.append("public.f_unaccent(c.city) ILIKE public.f_unaccent(:city)")
            params["city"] = city
        if neighborhood:
            conds.append(
                "public.f_unaccent(c.neighborhood) ILIKE public.f_unaccent(:nb)"
            )
            params["nb"] = f"%{neighborhood}%"
        if type_:
            conds.append("c.type = :ctype")
            params["ctype"] = type_
        if tag:
            conds.append("c.tags @> CAST(:tag AS jsonb)")
            params["tag"] = _json.dumps([tag])
        where = " AND ".join(conds)

        src = (
            "demands d JOIN contacts c ON c.id = d.contact_id"
            if metric == "demands"
            else "contacts c"
        )
        cnt = "count(d.id)" if metric == "demands" else "count(*)"

        # Posição da bolha:
        #  - bairro: média das coordenadas dos contatos do grupo.
        #  - local de votação: coordenada REAL do local (base TSE), resolvida
        #    por município + nome do local. Assim a bolha aparece no ponto
        #    exato mesmo que os contatos NÃO estejam geocodificados (bairro
        #    conhecido não força marcar no mapa). LATERAL LIMIT 1 pega uma
        #    coordenada por contato sem inflar a contagem; cai de volta na
        #    coord do contato se o local não casar na base.
        if group_by == "voting_place":
            src += (
                " LEFT JOIN LATERAL ("
                "  SELECT tvp.latitude AS lat, tvp.longitude AS lng"
                "  FROM tse_voting_places tvp"
                "  JOIN tse_municipalities tm ON tm.id = tvp.municipality_id"
                "  WHERE tm.state = c.state"
                "    AND public.f_unaccent(tm.name) ILIKE public.f_unaccent(c.city)"
                "    AND public.f_unaccent(tvp.name) ILIKE public.f_unaccent(c.voting_place)"
                "    AND tvp.latitude IS NOT NULL AND tvp.longitude IS NOT NULL"
                "  LIMIT 1"
                ") vp ON true"
            )
            lat_expr = "avg(coalesce(vp.lat, c.latitude))"
            lng_expr = "avg(coalesce(vp.lng, c.longitude))"
        else:
            lat_expr = "avg(c.latitude)"
            lng_expr = "avg(c.longitude)"

        sql = (
            f"SELECT {key_expr} AS key, {cnt} AS cnt, "
            f"  {lat_expr} AS lat, {lng_expr} AS lng "
            f"FROM {src} WHERE {where} "
            f"GROUP BY key ORDER BY cnt DESC LIMIT 200"
        )
        rows = self._ctx.db.execute(_text(sql), params).mappings().all()
        return [
            {
                "key": r["key"],
                "count": int(r["cnt"]),
                "lat": float(r["lat"]) if r["lat"] is not None else None,
                "lng": float(r["lng"]) if r["lng"] is not None else None,
            }
            for r in rows
        ]

    def list_contact_interactions(
        self,
        contact_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Interaction], int]:
        """
        Timeline de interacoes (webhooks) de um contato.

        REUSO ESTRATEGICO: chamamos get_contact() primeiro — ele ja' levanta
        NotFoundError se o contato nao pertence ao tenant. Sem duplicar
        regra de validacao. Se get_contact passou, podemos confiar que o
        contact_id e' do nosso tenant.
        """
        self.get_contact(contact_id)  # 404 se nao for nosso

        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        repo = InteractionRepository(self._ctx.db)
        items = repo.list_by_contact(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
            limit=limit,
            offset=offset,
        )
        total = repo.count_by_contact(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
        )
        return items, total

    # ---------------------------------------------------------------- Update

    def update_contact(
        self,
        contact_id: UUID,
        payload: ContactUpdate,
        background_tasks: BackgroundTasks | None = None,
    ) -> Contact:
        current = self.get_contact(contact_id)
        self._assert_can_edit(current)

        data = payload.model_dump(exclude_unset=True)
        new_phone = data.get("phone")
        if new_phone and new_phone != current.phone:
            if self._repo.exists_by_phone(
                tenant_id=self._ctx.tenant_id,
                phone=new_phone,
                exclude_id=contact_id,
            ):
                raise ConflictError("Ja existe outro contato com este telefone.")

        # Detecta mudanca de endereco — se mudou e lat/lng NAO foram fornecidos
        # explicitamente neste payload, vamos re-geocodificar
        address_fields = {"address", "neighborhood", "city", "state"}
        address_changed = any(
            f in data and data[f] != getattr(current, f) for f in address_fields
        )
        coords_provided = "latitude" in data or "longitude" in data

        updated = self._repo.update(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
            data=data,
        )
        if updated is None:
            raise NotFoundError("Contato nao encontrado.")
        record_audit(
            self._ctx,
            action="update",
            entity_type="contact",
            entity_id=contact_id,
            summary=f"Editou contato {updated.full_name}",
            meta={"campos": list(data.keys())},
        )
        self._ctx.db.commit()

        log.info(
            "contact_updated",
            tenant_id=str(self._ctx.tenant_id),
            contact_id=str(contact_id),
            fields=list(data.keys()),
        )

        # Re-geocoda apenas se: endereco mudou E nao vieram coords no payload
        if address_changed and not coords_provided:
            _schedule_geocoding(background_tasks, updated)

        return updated

    # ---------------------------------------------------------------- Import

    # Limite maximo de erros que retornamos ao cliente (truncado)
    _MAX_ERRORS_RETURNED = 50

    def import_csv_contacts(self, file_bytes: bytes) -> ImportResult:
        """
        Import bulk via CSV.

        Estrategia (ver csv_import.py para parser + normalizacao):
        1. Parse + validacao linha-a-linha
        2. Dedup intra-arquivo por telefone (rejeita duplicatas dentro do CSV)
        3. Query unica buscando telefones ja existentes no tenant (rejeita)
        4. Bulk insert do que sobrou (UM INSERT VALUES (...))
        5. SEM geocoding — seria 1 req/s no Nominatim e travaria 1000 contatos
           em ~17 min. Geocoding em lote sera job futuro.
        """
        rows, errors = parse_csv(file_bytes)
        total_rows = len(rows) + len(errors)

        # --- 2. Dedup intra-arquivo por telefone --------------------------
        seen_phones: set[str] = set()
        candidates: list[tuple[int, dict]] = []
        for idx, row in enumerate(rows, start=2):  # linha 2 = primeira de dados
            phone = row.get("phone")
            if phone and phone in seen_phones:
                errors.append(
                    ImportRowError(
                        row=idx,
                        message=f"Telefone duplicado no proprio CSV: {phone}",
                    )
                )
                continue
            if phone:
                seen_phones.add(phone)
            candidates.append((idx, row))

        # --- 3. Telefones ja existentes no tenant (1 query) ---------------
        existing_phones = self._repo.find_existing_phones(
            tenant_id=self._ctx.tenant_id,
            phones=list(seen_phones),
        )
        to_insert: list[dict] = []
        for idx, row in candidates:
            phone = row.get("phone")
            if phone and phone in existing_phones:
                errors.append(
                    ImportRowError(
                        row=idx,
                        message=f"Telefone ja cadastrado: {phone}",
                    )
                )
                continue
            to_insert.append(row)

        # --- 4. Bulk insert ------------------------------------------------
        inserted = self._repo.bulk_create(
            tenant_id=self._ctx.tenant_id,
            rows=to_insert,
            created_by_user_id=self._ctx.user_id,
            created_by_name=self._ctx.user_name or None,
        )
        if inserted:
            record_audit(
                self._ctx,
                action="create",
                entity_type="contact",
                summary=f"Importou {inserted} contato(s) via CSV",
                meta={"importados": inserted, "ignorados": len(errors)},
            )
        self._ctx.db.commit()

        log.info(
            "contacts_imported",
            tenant_id=str(self._ctx.tenant_id),
            user_id=str(self._ctx.user_id),
            total_rows=total_rows,
            imported=inserted,
            skipped=len(errors),
        )

        return ImportResult(
            imported=inserted,
            skipped=len(errors),
            total_rows=total_rows,
            errors=errors[: self._MAX_ERRORS_RETURNED],
        )

    # ---------------------------------------------------------------- Delete

    def delete_contact(self, contact_id: UUID) -> None:
        """
        SOFT DELETE: marca is_active=False. Cliente ve' o mesmo comportamento
        (some das listas, GET retorna 404), mas integridade referencial e'
        preservada — interactions e demands continuam validas.
        """
        # Busca antes do delete: precisamos do nome (auditoria) e do dono
        # (regra "Comum edita só o que enviou" — checada em _assert_can_edit).
        contact = self.get_contact(contact_id)
        self._assert_can_edit(contact)
        ok = self._repo.soft_delete(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
        )
        if not ok:
            # Nao existe OU ja' estava inativo: mesma resposta 404.
            raise NotFoundError("Contato nao encontrado.")
        record_audit(
            self._ctx,
            action="delete",
            entity_type="contact",
            entity_id=contact_id,
            summary=f"Excluiu contato {contact.full_name}",
        )
        self._ctx.db.commit()
        log.info(
            "contact_soft_deleted",
            tenant_id=str(self._ctx.tenant_id),
            contact_id=str(contact_id),
        )
