"""
Service de autenticacao.

Regra critica: mensagens de erro NUNCA revelam se foi "email errado",
"senha errada" ou "tenant inexistente" — sempre "credenciais invalidas".
Isso evita user enumeration.
"""
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import (
    AmbiguousLoginError,
    NotFoundError,
    TrialExpiredError,
    UnauthorizedError,
)
from app.core.security import (
    capped_token_delta,
    create_access_token,
    hash_password,
    verify_password,
)
from app.core.tenant_context import TenantContext
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, MeResponse, TokenResponse

log = structlog.get_logger("marenostrum.services.auth")

# Hash "fantasma" usado quando o usuario nao existe, para que a duracao
# da resposta seja parecida com a do caso valido (mitiga timing attack).
_DUMMY_HASH = hash_password("dummy-password-for-constant-time")


class AuthService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._users = UserRepository(db)

    def _diagnose_missing(self, email: str, tenant_slug: str | None) -> str:
        """Por que não achamos uma linha ATIVA pra este e-mail? Só pra log.

        Distingue os casos que, pro cliente, aparecem todos como "Credenciais
        inválidas": e-mail inexistente, conta desativada, campanha desativada
        ou campanha errada. Sem isso, todo suporte vira adivinhação.
        """
        from app.models.tenant import Tenant
        from app.models.user import User

        rows = (
            self._db.query(User, Tenant)
            .join(Tenant, Tenant.id == User.tenant_id)
            .filter(User.email == email)
            .all()
        )
        if not rows:
            return "user_not_found"
        if not any(u.is_active for u, _ in rows):
            return "user_inactive"
        if not any(t.is_active for _, t in rows):
            return "tenant_inactive"
        if tenant_slug and not any(t.slug == tenant_slug for _, t in rows):
            # Existe e está ativo, mas em OUTRA campanha (era o caso do
            # formulário com slug fixo).
            return "wrong_tenant"
        return "no_active_row"

    def login(self, payload: LoginRequest) -> TokenResponse:
        # Motivo REAL da falha — só pro log estruturado. A resposta ao cliente
        # continua sendo sempre "Credenciais invalidas" (anti-enumeração).
        reason = "unknown"

        if payload.tenant_slug:
            # Caminho explícito (API/integrações): campanha informada.
            user = self._users.get_by_email_and_tenant_slug(
                email=payload.email,
                tenant_slug=payload.tenant_slug,
            )
            valid_password = verify_password(
                payload.password,
                user.hashed_password if user else _DUMMY_HASH,
            )
            if user is None:
                # Sem linha ATIVA nesta campanha: e-mail inexistente, usuário
                # desativado, campanha errada ou campanha desativada.
                reason = self._diagnose_missing(payload.email, payload.tenant_slug)
            elif not valid_password:
                reason = "password_mismatch"
        else:
            # Caminho do formulário: descobre a campanha pelo e-mail + senha.
            # O cliente não conhece o slug dele — exigir isso deixava qualquer
            # conta fora da campanha padrão SEM CONSEGUIR ENTRAR.
            candidates = self._users.list_active_by_email(email=payload.email)
            matches = [
                u for u, _ in candidates
                if verify_password(payload.password, u.hashed_password)
            ]
            if not candidates:
                # Nenhum usuário: gasta um hash mesmo assim (timing constante).
                verify_password(payload.password, _DUMMY_HASH)
            if len(matches) > 1:
                # Mesmo e-mail+senha em campanhas diferentes: quem escolhe é o
                # usuário — o backend não adivinha em qual ele quer entrar.
                raise AmbiguousLoginError(
                    "Este e-mail tem acesso a mais de uma campanha. "
                    "Escolha em qual deseja entrar.",
                    options=[
                        {"tenant_slug": t.slug, "tenant_name": t.name}
                        for u, t in candidates
                        if any(u.id == m.id for m in matches)
                    ],
                )
            user = matches[0] if matches else None
            valid_password = user is not None
            if user is None:
                reason = (
                    "password_mismatch" if candidates
                    else self._diagnose_missing(payload.email, None)
                )

        if user is None or not valid_password:
            # `reason` distingue e-mail inexistente / conta desativada /
            # campanha desativada / senha errada — indispensável pra suporte,
            # e NUNCA vai pro JSON de resposta.
            log.info(
                "login_failed",
                reason=reason,
                tenant_slug=payload.tenant_slug,
                email=payload.email,
            )
            raise UnauthorizedError("Credenciais invalidas")

        settings = get_settings()
        now = datetime.now(timezone.utc)

        # ------------------------------------------------ Acesso temporário
        # O relógio do trial só começa AGORA, no 1º login (não na criação).
        limit = getattr(user, "usage_limit_hours", None)
        if limit and limit > 0:
            if user.first_login_at is None:
                # 1º login: inicia o relógio e materializa a expiração absoluta.
                user.first_login_at = now
                user.expires_at = now + timedelta(hours=float(limit))
                self._users.save(user)
                log.info(
                    "trial_started",
                    user_id=str(user.id),
                    expires_at=user.expires_at.isoformat(),
                )
            # Bloqueio: se já expirou, nega o login (403 dedicado).
            elif capped_token_delta(user.expires_at, now, timedelta(days=1)) is None:
                log.info("trial_expired_login_blocked", user_id=str(user.id))
                raise TrialExpiredError("Seu período de uso expirou.")

        # JWT nunca vive além do expires_at do trial. `not_after` é o teto
        # ABSOLUTO (garante exp <= expires_at ao ms); o expires_delta define o
        # TTL do cookie (min entre o padrão e o restante do trial).
        default_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        expires_delta = (
            capped_token_delta(user.expires_at, now, default_delta) or default_delta
        )

        token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role.value,
            expires_delta=expires_delta,
            not_after=user.expires_at,
        )

        log.info(
            "login_success",
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
        )

        return TokenResponse(
            access_token=token,
            expires_in=int(expires_delta.total_seconds()),
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role.value,
        )

    @staticmethod
    def me(ctx: TenantContext) -> MeResponse:
        """Dados do usuario logado + tenant. Prova end-to-end do JWT."""
        repo = UserRepository(ctx.db)
        if getattr(ctx, "is_impersonating", False):
            # ACESSO MARE NOSTRUM: usuário e tenant são de origens DIFERENTES
            # de propósito (superadmin visitando o cliente), então o JOIN
            # "usuário pertence ao tenant" não se aplica — busca separada.
            from app.models.tenant import Tenant
            from app.models.user import User as _User

            user = ctx.db.get(_User, ctx.user_id)
            tenant = ctx.db.get(Tenant, ctx.tenant_id)
            if user is None or tenant is None:
                raise NotFoundError("Usuario nao encontrado")
        else:
            row = repo.get_with_tenant(user_id=ctx.user_id, tenant_id=ctx.tenant_id)
            if row is None:
                # Caso raro: token valido mas user/tenant deletado entre auth e /me
                raise NotFoundError("Usuario nao encontrado")
            user, tenant = row
        return MeResponse(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            tenant_name=tenant.name,
            is_superadmin=bool(getattr(user, "is_superadmin", False)),
            impersonating=bool(getattr(ctx, "is_impersonating", False)),
            census_enabled=bool(getattr(user, "census_enabled", False)),
            analytics_enabled=bool(getattr(user, "analytics_enabled", True)),
            panel_enabled=bool(getattr(user, "panel_enabled", True)),
            map_enabled=bool(getattr(user, "map_enabled", True)),
            demands_enabled=bool(getattr(user, "demands_enabled", True)),
            agenda_enabled=bool(getattr(user, "agenda_enabled", True)),
            # Trial: expiração absoluta (pro frontend avisar e pro cap do refresh).
            trial_expires_at=getattr(user, "expires_at", None),
        )
