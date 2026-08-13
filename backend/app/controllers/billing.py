"""
Controller de billing (assinatura Asaas).

- POST /billing/checkout           PÚBLICO  (comprador ainda não tem conta)
- POST /billing/webhook/asaas      PÚBLICO  (autenticado por token no header)
- GET  /billing/me                 PRIVADO  (tela de paywall do /sistema)

O webhook e o checkout NÃO usam CurrentTenant e DEVEM ficar isentos do gate de
assinatura (senão o comprador nem paga). O /me é isento do bloqueio 402 pra a
tela de "regularizar pagamento" conseguir renderizar.
"""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant
from app.core.errors import DomainError
from app.schemas.billing import (
    AsaasWebhookPayload,
    BillingMeResponse,
    BillingWebhookAck,
    CheckoutRequest,
    CheckoutResponse,
)
from app.services.asaas import AsaasError
from app.services.billing import BillingService
from app.services.email import send_set_password_email
from app.utils.rate_limit import limiter

router = APIRouter(prefix="/billing", tags=["billing"])


class _BillingUnavailable(DomainError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "billing_unavailable"


class _WebhookUnauthorized(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Iniciar assinatura (cria cobrança no Asaas e devolve o link)",
    description="""\
**Público** (o comprador ainda não tem conta). Cria o cliente + a assinatura
MENSAL no Asaas e devolve `invoice_url` (página de pagamento hospedada, onde o
comprador escolhe PIX/boleto/cartão). O **preço é fixado no backend** — o valor
enviado pelo cliente é ignorado. A liberação do acesso acontece depois, pelo
webhook, quando o pagamento confirma.
""",
)
@limiter.limit("10/minute")
def create_checkout(
    request: Request,
    payload: CheckoutRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CheckoutResponse:
    try:
        return BillingService(db).create_checkout(payload)
    except AsaasError as exc:
        # billing desligado (sem chave) OU falha na API do Asaas.
        raise _BillingUnavailable(
            "Não foi possível iniciar o pagamento agora. Tente novamente em instantes."
        ) from exc


@router.post(
    "/webhook/asaas",
    response_model=BillingWebhookAck,
    summary="Webhook do Asaas (eventos de pagamento)",
    description="""\
**Público**, autenticado pelo header `asaas-access-token` (comparação
constant-time com o token cadastrado). Responde **200** sempre que o token bate
(mesmo em evento duplicado/ignorado) pra não travar a fila SEQUENTIALLY do Asaas.
Idempotente por event id. Em `PAYMENT_CONFIRMED`/`RECEIVED` provisiona o tenant
e libera o acesso; `PAYMENT_OVERDUE` entra em tolerância; reembolso/cancelamento
suspende.
""",
)
@limiter.limit("120/minute")
def asaas_webhook(
    request: Request,
    background: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[AsaasWebhookPayload, Body(...)],
    asaas_access_token: Annotated[
        str | None,
        Header(alias="asaas-access-token", description="Token do webhook (constant-time)."),
    ] = None,
) -> BillingWebhookAck:
    outcome = BillingService(db).process_webhook(
        token_provided=asaas_access_token, payload=payload
    )
    if outcome is None:
        raise _WebhookUnauthorized("Token de webhook inválido.")
    # E-mail do link de senha em BACKGROUND: a resposta 200 sai na hora (a fila
    # do Asaas é sequencial — não pode esperar SMTP).
    if outcome.email_to and outcome.set_password_link:
        background.add_task(
            send_set_password_email,
            to=outcome.email_to,
            name=outcome.email_name or "",
            link=outcome.set_password_link,
        )
    return outcome.ack


@router.get(
    "/me",
    response_model=BillingMeResponse,
    summary="Estado da assinatura do tenant logado (paywall)",
)
def billing_me(ctx: CurrentTenant) -> BillingMeResponse:
    return BillingService(ctx.db).get_status_for_tenant(ctx.tenant_id)
