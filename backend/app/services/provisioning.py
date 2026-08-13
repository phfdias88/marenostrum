"""
Provisionamento de conta a partir de uma COMPRA.

Quando o 1º pagamento de uma assinatura confirma (webhook do Asaas), o comprador
vira um TENANT no nosso SaaS com um usuário OWNER. É a versão "self-service" do
que o `app/utils/seed.py` faz manualmente — extraída aqui pra ser chamada pelo
webhook de billing.

Idempotente: chamar duas vezes pra a mesma assinatura (o Asaas entrega eventos
"pelo menos uma vez") NÃO cria tenant/owner duplicado. A trava principal é o
`Subscription.tenant_id` (se já preenchido, a conta já existe); a secundária é o
UNIQUE (tenant_id, email) do owner.

O owner nasce com uma senha aleatória forte (que ninguém conhece) — o comprador
define a própria senha depois, via link de definição enviado por e-mail. O
pacote "Completo" liga todas as áreas + censo.
"""
from __future__ import annotations

import re
import secrets
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User, UserRole

# Slug: minúsculas, sem acento, só [a-z0-9-]. Limite abaixo do String(60) do
# tenant, deixando folga pro sufixo de desambiguação.
_SLUG_MAX = 48


def slugify(text: str) -> str:
    """'Dr. João Águia (2026)' -> 'dr-joao-aguia-2026'. Nunca vazio."""
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:_SLUG_MAX].strip("-")
    return slug or "cliente"


def _unique_slug(db: Session, base: str) -> str:
    """Garante unicidade em tenants.slug com sufixo determinístico crescente."""
    candidate = base
    n = 1
    while db.execute(
        select(Tenant.id).where(Tenant.slug == candidate)
    ).first() is not None:
        n += 1
        suffix = f"-{n}"
        candidate = f"{base[: _SLUG_MAX - len(suffix)]}{suffix}"
    return candidate


class ProvisioningResult:
    """Resultado de provisionar: o tenant, o owner e se acabou de ser criado."""

    __slots__ = ("tenant", "owner", "created")

    def __init__(self, tenant: Tenant, owner: User, created: bool) -> None:
        self.tenant = tenant
        self.owner = owner
        self.created = created


def provision_from_subscription(db: Session, subscription: Subscription) -> ProvisioningResult:
    """
    Cria (ou recupera) o tenant + owner desta assinatura. NÃO commita — o caller
    (webhook) controla a transação junto do update de status/idempotência.

    Requer `subscription.buyer_name` e `subscription.billing_email`.
    """
    email = (subscription.billing_email or "").strip().lower()
    name = (subscription.buyer_name or "").strip()
    if not email or not name:
        raise ValueError(
            "Assinatura sem buyer_name/billing_email — não dá pra provisionar."
        )

    # 1) Já provisionado? (idempotência primária)
    if subscription.tenant_id is not None:
        tenant = db.get(Tenant, subscription.tenant_id)
        if tenant is not None:
            owner = db.execute(
                select(User).where(
                    User.tenant_id == tenant.id, User.email == email
                )
            ).scalar_one_or_none()
            if owner is not None:
                return ProvisioningResult(tenant, owner, created=False)

    # 2) Cria o tenant (slug único derivado do nome do comprador/candidato).
    tenant = Tenant(
        name=name[:120],
        slug=_unique_slug(db, slugify(name)),
        is_active=True,
        subscription_status="active",
    )
    db.add(tenant)
    db.flush()  # materializa tenant.id

    # 3) Owner com senha aleatória forte (o comprador define a dele via link).
    #    Idempotência secundária: se por algum motivo o email já existir no
    #    tenant, reaproveita.
    owner = db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == email)
    ).scalar_one_or_none()
    created = False
    if owner is None:
        owner = User(
            tenant_id=tenant.id,
            email=email,
            full_name=name[:150],
            hashed_password=hash_password(secrets.token_urlsafe(24)),
            role=UserRole.OWNER,
            is_active=True,
            # TITULAR: este usuário nasceu de uma COMPRA (webhook Asaas) — é
            # quem paga a conta. Convidados do painel nascem False.
            is_account_owner=True,
            # Pacote "Completo": tudo ligado.
            census_enabled=True,
            analytics_enabled=True,
            panel_enabled=True,
            map_enabled=True,
            demands_enabled=True,
            agenda_enabled=True,
        )
        db.add(owner)
        db.flush()
        created = True

    # 4) Liga a assinatura ao tenant recém-criado.
    subscription.tenant_id = tenant.id

    return ProvisioningResult(tenant, owner, created=created)
