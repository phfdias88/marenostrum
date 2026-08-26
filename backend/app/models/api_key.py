"""
Chave de acesso programatico a API (somente leitura).

Existe porque a alternativa era pior: sem ela, integrar um BI significaria
guardar a SENHA de um usuario num script e refazer login sozinho — e revogar
o acesso obrigaria a trocar essa senha, derrubando a pessoa junto.

A chave em si NUNCA e guardada: gravamos o SHA-256. O `prefix` (primeiros
caracteres) serve pra identificar a chave numa listagem sem permitir
reconstrui-la. Quem cria ve o valor UMA vez, na resposta da criacao.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # SHA-256 em hexadecimal (64 caracteres). Unico: e por ele que a
    # autenticacao encontra a chave a cada request.
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # So pra exibir ("mn_live_a1b2…"). Nao permite reconstruir a chave.
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    # Hoje so existe "read". Deixado como texto pra crescer sem migration.
    scopes: Mapped[str] = mapped_column(String(200), nullable=False, default="read")

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def is_valid(self) -> bool:
        """Chave utilizavel: nem revogada, nem vencida."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            # O banco devolve datetime aware em Postgres e naive no SQLite dos
            # testes; normalizar evita "can't compare offset-naive and aware".
            venc = self.expires_at
            if venc.tzinfo is None:
                venc = venc.replace(tzinfo=timezone.utc)
            if venc <= datetime.now(timezone.utc):
                return False
        return True

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ApiKey {self.prefix}… {self.name!r}>"
