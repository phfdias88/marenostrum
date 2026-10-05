"""
Orquestração do billing recorrente (Asaas) — a lógica de dinheiro fica AQUI,
o controller só chama.

Dois fluxos:
1. `create_checkout`: cria cliente + assinatura mensal no Asaas e devolve a URL
   de pagamento. O PREÇO é do backend (settings), nunca do cliente.
2. `process_webhook`: recebe o evento do Asaas, faz dedup (idempotência), casa
   com a assinatura e transiciona status (ativa/provisiona, past_due, cancela).

Regras de ouro (Asaas entrega "pelo menos uma vez", fila SEQUENTIALLY trava no
1º não-2xx): idempotência por event id + responder 200 sempre que o token bate.
"""
from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import create_set_password_token, password_fingerprint
from app.models.subscription import BillingEvent, Subscription
from app.models.tenant import Tenant
from app.schemas.billing import (
    BillingMeResponse,
    BillingWebhookAck,
    CheckoutRequest,
    CheckoutResponse,
)
from app.services.asaas import AsaasClient, AsaasError, get_asaas_client
from app.services.provisioning import ProvisioningResult, provision_from_subscription


@dataclass
class WebhookOutcome:
    """Resultado do webhook. `ack` vira a resposta 200; se houver e-mail a
    enviar (owner recém-provisionado), o controller dispara em background pra
    não segurar a resposta (a fila do Asaas é sequencial)."""
    ack: BillingWebhookAck
    email_to: str | None = None
    email_name: str | None = None
    set_password_link: str | None = None

# Eventos que LIBERAM acesso (confirmado no cartão / recebido no PIX-boleto).
_ACTIVATE_EVENTS = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}
# Atraso: entra em tolerância, ainda não bloqueia.
_OVERDUE_EVENTS = {"PAYMENT_OVERDUE"}
# Reversões / cancelamento → suspende/cancela o acesso.
_CANCEL_EVENTS = {
    "PAYMENT_REFUNDED",
    "PAYMENT_CHARGEBACK_REQUESTED",
    "PAYMENT_CHARGEBACK_DISPUTE",
    "SUBSCRIPTION_DELETED",
    "SUBSCRIPTION_INACTIVATED",
}


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _parse_due(value: str | None) -> datetime | None:
    """'YYYY-MM-DD' do Asaas → datetime tz-aware (meia-noite UTC)."""
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class BillingService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    # ------------------------------ Checkout ------------------------------
    def create_checkout(
        self, req: CheckoutRequest, *, client: AsaasClient | None = None
    ) -> CheckoutResponse:
        s = self.settings
        client = client or get_asaas_client()  # AsaasError se billing desligado

        ext_ref = uuid4().hex  # nosso elo Asaas↔nós (volta no webhook)
        sub = Subscription(
            status="pending",
            plan=s.BILLING_PLAN_SLUG,
            cycle=s.BILLING_PLAN_CYCLE,
            value=Decimal(str(s.BILLING_PLAN_VALUE)),
            external_reference=ext_ref,
            billing_email=req.email.strip().lower(),
            buyer_name=req.name.strip(),
            buyer_cpf_cnpj=_digits(req.cpf_cnpj),
            uf=(req.uf or None),
            municipality=(req.municipality or None),
        )
        self.db.add(sub)
        self.db.flush()

        customer = client.create_customer(
            name=req.name.strip(),
            cpf_cnpj=_digits(req.cpf_cnpj),
            email=req.email.strip().lower(),
            mobile_phone=_digits(req.phone) or None,
            external_reference=ext_ref,
        )
        sub.asaas_customer_id = customer.get("id")

        subscription = client.create_subscription(
            customer_id=customer["id"],
            value=float(s.BILLING_PLAN_VALUE),
            cycle=s.BILLING_PLAN_CYCLE,
            billing_type="UNDEFINED",  # comprador escolhe PIX/boleto/cartão
            description=s.BILLING_PLAN_NAME,
            external_reference=ext_ref,
        )
        sub.asaas_subscription_id = subscription.get("id")

        invoice_url = client.first_invoice_url(subscription["id"])
        self.db.commit()

        if not invoice_url:
            raise AsaasError("Assinatura criada, mas o Asaas não devolveu a URL de pagamento.")
        return CheckoutResponse(invoice_url=invoice_url, external_reference=ext_ref)

    # ------------------------------ Webhook -------------------------------
    def process_webhook(
        self, *, token_provided: str | None, payload: dict
    ) -> WebhookOutcome | None:
        """Retorna None se o token for inválido (o controller devolve 401);
        senão devolve um WebhookOutcome (200 sempre — não travar a fila)."""
        expected = self.settings.ASAAS_WEBHOOK_TOKEN
        if not expected or not token_provided or not hmac.compare_digest(
            str(token_provided), str(expected)
        ):
            return None  # → 401 no controller

        event = payload.get("event")
        payment = payload.get("payment") or {}
        sub_payload = payload.get("subscription") or {}
        evt_id = payload.get("id") or (
            f"{event}:{payment.get('id') or sub_payload.get('id') or ''}"
        )

        # Idempotência: 1 linha por event id. Se já existe → duplicado → 200.
        self.db.add(BillingEvent(asaas_event_id=evt_id, event_type=event, payload=payload))
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            return WebhookOutcome(BillingWebhookAck(status="ignored_duplicate"))

        sub = self._find_subscription(payment, sub_payload)
        if sub is None:
            self.db.commit()  # guarda o billing_event mesmo sem casar
            return WebhookOutcome(BillingWebhookAck(status="unmatched"))

        sub.last_event_id = evt_id
        if payment.get("id"):
            sub.last_payment_id = payment["id"]
        now = datetime.now(timezone.utc)
        email_to = email_name = set_password_link = None

        if event in _ACTIVATE_EVENTS:
            if sub.tenant_id is None:
                result: ProvisioningResult = provision_from_subscription(self.db, sub)
                self.db.flush()
                # Owner novo → gera o link de definição de senha (uso único) que
                # o controller envia por e-mail em background.
                if result.created:
                    token = create_set_password_token(
                        user_id=result.owner.id,
                        tenant_id=result.tenant.id,
                        tenant_slug=result.tenant.slug,
                        fingerprint=password_fingerprint(result.owner.hashed_password),
                    )
                    base = str(getattr(self.settings, "PUBLIC_URL_BASE", "")).rstrip("/")
                    set_password_link = f"{base}/set-password?token={token}"
                    email_to = result.owner.email
                    email_name = result.owner.full_name
            sub.status = "active"
            sub.current_period_end = _parse_due(payment.get("dueDate")) or sub.current_period_end
            self._set_tenant(sub, status="active", grace_until=None)
        elif event in _OVERDUE_EVENTS:
            sub.status = "past_due"
            self._set_tenant(
                sub,
                status="past_due",
                grace_until=now + timedelta(days=self.settings.BILLING_GRACE_DAYS),
            )
        elif event in _CANCEL_EVENTS:
            sub.status = "canceled"
            self._set_tenant(sub, status="canceled", grace_until=None)
        # else: evento não tratado — ainda respondemos 200 (não travar a fila).

        self.db.commit()
        return WebhookOutcome(
            BillingWebhookAck(status="processed"),
            email_to=email_to,
            email_name=email_name,
            set_password_link=set_password_link,
        )

    # ------------------------------ /me -----------------------------------
    def get_status_for_tenant(self, tenant_id) -> BillingMeResponse:
        sub = self.db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
        ).scalars().first()
        tenant = self.db.get(Tenant, tenant_id)
        status = tenant.subscription_status if tenant else "none"
        return BillingMeResponse(
            status=status,
            plan=(sub.plan if sub else None),
            current_period_end=(sub.current_period_end if sub else None),
        )

    # ------------------------------ helpers -------------------------------
    def _find_subscription(self, payment: dict, sub_payload: dict) -> Subscription | None:
        ext_ref = payment.get("externalReference") or sub_payload.get("externalReference")
        if ext_ref:
            sub = self.db.execute(
                select(Subscription).where(Subscription.external_reference == ext_ref)
            ).scalar_one_or_none()
            if sub is not None:
                return sub
        asaas_sub_id = payment.get("subscription") or sub_payload.get("id")
        if asaas_sub_id:
            return self.db.execute(
                select(Subscription).where(Subscription.asaas_subscription_id == asaas_sub_id)
            ).scalar_one_or_none()
        return None

    def _set_tenant(self, sub: Subscription, *, status: str, grace_until) -> None:
        if sub.tenant_id is None:
            return
        tenant = self.db.get(Tenant, sub.tenant_id)
        if tenant is not None:
            tenant.subscription_status = status
            tenant.grace_until = grace_until
