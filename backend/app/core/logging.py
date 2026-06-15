"""Logs estruturados (JSON em prod, console em dev)."""
import logging
import sys
from datetime import datetime, timedelta, timezone

import structlog

from app.config import get_settings

# Horário de Brasília (UTC-3). Offset fixo: o Brasil não tem horário de verão
# desde 2019, então não precisamos do tzdata no container — e o log fica no
# fuso de quem opera o sistema, sem ter que subtrair 3h de cabeça.
_BRT = timezone(timedelta(hours=-3))


def _brasilia_timestamp(_, __, event_dict: dict) -> dict:
    """Carimba o evento com o horário de Brasília (ISO, ex: 2026-06-15T18:46:35-03:00)."""
    event_dict["timestamp"] = datetime.now(_BRT).isoformat(timespec="seconds")
    return event_dict


def setup_logging() -> None:
    settings = get_settings()
    is_prod = settings.APP_ENV == "production"

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _brasilia_timestamp,  # horário de Brasília em vez de UTC
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if is_prod
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
