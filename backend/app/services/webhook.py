"""
Service de webhooks externos (BotConversa, etc).

SEGURANCA:
- Comparacao de secret via hmac.compare_digest (constant-time).
  Comparar com `==` permitiria timing-attack descobrindo secret byte a byte.
- Per-tenant secret preferido; fallback global so em DEV ou tenants
  ainda nao configurados.

RESILIENCIA (CRITICO PARA WEBHOOKS):
- Payload aceito como dict cru — fornecedores mudam estrutura sem aviso.
- Helpers _extract_* tentam varios campos comuns. Se nao acharem, salvam
  com NULL — interacao orfa e' melhor que recusar.
- Service NUNCA retorna erro pra payload malformado (so' pra auth/tenant).
  Webhook que recebe 5xx = provedor reenvia = duplicatas.
"""
import hmac
from typing import Any
from uuid import UUID

import structlog

from app.config import get_settings
from app.core.errors import NotFoundError, UnauthorizedError
from app.models.interaction import Interaction
from app.repositories.contact import ContactRepository
from app.repositories.interaction import InteractionRepository
from app.repositories.tenant import TenantRepository
from app.schemas.webhook import WebhookAck
from sqlalchemy.orm import Session

log = structlog.get_logger("marenostrum.webhook")


# ----------------------------- extractors (BotConversa-friendly) ---------

# Campos comuns onde BotConversa coloca o telefone do contato.
# Tentamos em ordem — primeiro que tiver valor ganha.
_PHONE_KEYS = ("phone", "subscriber_phone", "telefone", "whatsapp", "from")
_EVENT_TYPE_KEYS = ("event", "event_type", "type", "action")
_EXTERNAL_ID_KEYS = ("event_id", "id", "uuid", "message_id")


def _find_first(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Procura por keys top-level no payload e retorna a primeira nao-vazia."""
    for k in keys:
        v = payload.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def _extract_phone(payload: dict[str, Any]) -> str | None:
    # Top-level primeiro
    phone = _find_first(payload, _PHONE_KEYS)
    if phone:
        return phone.strip()
    # BotConversa as vezes aninha em 'subscriber'/'contact'
    for nested_key in ("subscriber", "contact", "from"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            phone = _find_first(nested, _PHONE_KEYS)
            if phone:
                return phone.strip()
    return None


# ------------------------------------------------------------------ service


class WebhookService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._tenants = TenantRepository(db)
        self._contacts = ContactRepository(db)
        self._interactions = InteractionRepository(db)

    def process_botconversa_event(
        self,
        *,
        tenant_id: UUID,
        secret_provided: str | None,
        payload: dict[str, Any],
    ) -> WebhookAck:
        # 1. Tenant existe e ativo?
        tenant = self._tenants.get_active(tenant_id=tenant_id)
        if tenant is None:
            # 404 NEUTRO — nao revela se eh "nao existe" vs "inativo"
            raise NotFoundError("Tenant nao encontrado")

        # 2. Valida secret (constant-time)
        self._validate_secret(
            tenant_secret=tenant.webhook_secret,
            provided=secret_provided,
        )

        # 3. Extrai campos do payload (tolerante a estruturas diferentes)
        phone = _extract_phone(payload)
        event_type = _find_first(payload, _EVENT_TYPE_KEYS)
        external_id = _find_first(payload, _EXTERNAL_ID_KEYS)

        # 4. Tenta linkar com contato. Se nao achar, fica orfa.
        contact_id: UUID | None = None
        if phone:
            contact = self._contacts.find_by_phone(
                tenant_id=tenant_id, phone=phone,
            )
            if contact is not None:
                contact_id = contact.id

        # 5. Persiste interacao
        interaction = self._interactions.create(
            tenant_id=tenant_id,
            contact_id=contact_id,
            phone=phone,
            event_type=event_type,
            channel="whatsapp",
            external_event_id=external_id,
            payload_data=payload,
        )
        self._db.commit()

        log.info(
            "webhook_received",
            tenant_id=str(tenant_id),
            interaction_id=str(interaction.id),
            contact_matched=contact_id is not None,
            phone=phone,
            event_type=event_type,
            external_id=external_id,
        )

        return WebhookAck(
            status="received",
            interaction_id=interaction.id,
            contact_matched=contact_id is not None,
            contact_id=contact_id,
        )

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _validate_secret(
        *,
        tenant_secret: str | None,
        provided: str | None,
    ) -> None:
        """
        Valida secret. Per-tenant tem precedencia; fallback pra global
        SOMENTE se tenant nao tem proprio.

        IMPORTANTE: hmac.compare_digest e' constant-time — anti timing attack.
        Comparar com `==` deixa atacante medir tempo de resposta pra
        descobrir secret byte a byte.
        """
        expected = tenant_secret or get_settings().WEBHOOK_GLOBAL_SECRET

        if not expected:
            # Tenant sem secret + sem fallback global = webhook desabilitado
            raise UnauthorizedError("Webhook nao configurado para este tenant")

        if not provided or not hmac.compare_digest(provided, expected):
            raise UnauthorizedError("Secret invalido")
