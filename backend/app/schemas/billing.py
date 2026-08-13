"""Schemas do billing (checkout de assinatura + webhook do Asaas)."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    """Dados do comprador. O PREÇO não vem daqui — é fixado no backend (settings)."""
    # nome do comprador = nome do candidato = nome/slug do tenant provisionado.
    name: str = Field(..., min_length=2, max_length=150)
    cpf_cnpj: str = Field(..., min_length=11, max_length=20)
    email: str = Field(..., min_length=5, max_length=254)
    phone: str | None = Field(default=None, max_length=20)
    uf: str | None = Field(default=None, max_length=2)
    municipality: str | None = Field(default=None, max_length=120)


class CheckoutResponse(BaseModel):
    invoice_url: str          # página de pagamento hospedada do Asaas
    external_reference: str   # nosso elo (aparece no webhook)


class BillingWebhookAck(BaseModel):
    # received | ignored_duplicate | unmatched | processed
    status: str


class BillingMeResponse(BaseModel):
    """Estado da assinatura do tenant logado — alimenta a tela de paywall."""
    status: str                          # active | past_due | suspended | canceled | none
    plan: str | None = None
    current_period_end: datetime | None = None
    invoice_url: str | None = None       # link pra regularizar, se houver


# Payload do webhook do Asaas: dict cru (o formato pode variar por versão da API).
AsaasWebhookPayload = dict[str, Any]
