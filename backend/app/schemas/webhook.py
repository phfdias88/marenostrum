"""
Schemas para webhooks externos.

DECISAO: payload e' `dict[str, Any]` em vez de model estruturado.
Fornecedores (BotConversa, Zenvia, etc) mudam formato sem aviso. Aceitar
QUALQUER JSON e extrair campos via helpers e' mais resiliente que travar
em validacao estrita. Validacao real fica no service (extrai e valida o
que importa: phone, event_type, external_id).
"""
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class WebhookAck(BaseModel):
    """Resposta do webhook — devolvida pro provedor (BotConversa)."""
    status: str                          # "received" | "ignored_duplicate"
    interaction_id: UUID
    contact_matched: bool                # True se vinculou ao Contact
    contact_id: UUID | None = None


# Payload do BotConversa: aceito como dict cru. Helpers de extracao no
# service (services/webhook.py: _extract_phone, _extract_event_type, etc).
WebhookPayload = dict[str, Any]
