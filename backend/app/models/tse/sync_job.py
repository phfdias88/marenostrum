"""
TseSyncJob — rastreia jobs de sincronização TSE (download + parse + import).

Permite polling do status pela UI ("sincronizando 35%... pronto!").
Job é GLOBAL (qualquer admin de qualquer tenant pode disparar; afeta todos).
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SyncJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TseSyncJob(Base, TimestampMixin):
    __tablename__ = "tse_sync_jobs"

    # Qual dataset/ano sincronizado: 'candidatos_munzona_2024', 'partidos_munzona_2024'
    dataset: Mapped[str] = mapped_column(String(80), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[SyncJobStatus] = mapped_column(
        SAEnum(
            SyncJobStatus,
            name="tse_sync_job_status",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=SyncJobStatus.PENDING,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Progresso atual (linhas processadas) + total estimado
    rows_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Estatísticas finais
    candidates_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parties_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    municipalities_imported: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    vote_results_imported: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )

    # Erro (se status=failed)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
