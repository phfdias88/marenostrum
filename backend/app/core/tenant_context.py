"""
Contexto da request autenticada.

O `TenantContext` e construido UMA vez por request (via dependencia FastAPI)
e e o unico objeto que carrega `tenant_id`. Repositories recebem este contexto
e usam `ctx.tenant_id` para filtrar TODAS as queries.

Nao usamos contextvars globais de proposito: passar explicitamente reduz risco
de "vazar" tenant_id por engano (ex.: tarefa async de outro tenant pegar o
contextvar errado).
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Contexto imutavel da request. Frozen para evitar mutacao acidental."""
    user_id: UUID
    tenant_id: UUID
    role: str
    db: Session
    # Nome do usuário logado — usado pra carimbar "cadastrado por" no contato.
    user_name: str = ""
    # Feature-flags de acesso por área (owner sempre tem tudo — ver require_area).
    # Defaults amplos pra nao restringir caso o contexto seja montado sem eles.
    analytics_enabled: bool = True
    panel_enabled: bool = True
    map_enabled: bool = True
    demands_enabled: bool = True
    agenda_enabled: bool = True
    census_enabled: bool = False
