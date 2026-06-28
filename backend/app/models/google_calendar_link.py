"""
Vínculo do Google Calendar de UM usuário (read-only).

Guarda o refresh_token CIFRADO (Fernet) — nunca em claro. 1 linha por usuário
(cada pessoa conecta a própria agenda). tenant_id pra isolamento.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class GoogleCalendarLink(Base, TenantMixin, TimestampMixin):
    __tablename__ = "google_calendar_links"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    # refresh_token cifrado (Fernet) — base64, cabe folgado em 500.
    refresh_token_enc: Mapped[str] = mapped_column(String(500), nullable=False)
    google_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_google_cal_user"),
    )
