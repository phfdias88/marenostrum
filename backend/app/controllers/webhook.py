"""
Controller de webhooks externos.

ESTE ROUTER E' PUBLICO — NAO usa CurrentTenant (JWT).
Autenticacao via secret comparado em constant-time no service.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.webhook import WebhookAck, WebhookPayload
from app.services.webhook import WebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/botconversa/{tenant_id}",
    response_model=WebhookAck,
    summary="Recebe eventos do BotConversa (WhatsApp)",
    description=(
        "Endpoint PUBLICO. Autenticacao via secret no header "
        "`X-Webhook-Secret` (preferido) OU query `?secret=...` (fallback "
        "pra fornecedores que nao permitem custom header — atencao: "
        "query param fica em logs do proxy).\n\n"
        "Payload aceito como JSON arbitrario. Helpers no service tentam "
        "extrair `phone`, `event_type` e `external_event_id` de campos "
        "comuns; se nao acharem, salva como interacao orfa."
    ),
)
def receive_botconversa_event(
    tenant_id: UUID,
    payload: Annotated[WebhookPayload, Body(...)],
    db: Annotated[Session, Depends(get_db)],
    # Header preferido — nao vaza em logs do nginx/CDN
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
    # Fallback pra provedores que so' aceitam query string.
    # ATENCAO: query string aparece em access logs, considerar so pra dev.
    secret_query: Annotated[str | None, Query(alias="secret")] = None,
) -> WebhookAck:
    secret = x_webhook_secret or secret_query
    return WebhookService(db).process_botconversa_event(
        tenant_id=tenant_id,
        secret_provided=secret,
        payload=payload,
    )
