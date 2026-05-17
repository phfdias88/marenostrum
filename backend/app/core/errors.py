"""
Tratamento de erros centralizado: exceptions de dominio + handlers FastAPI.
Toda excecao de dominio vira HTTP de forma consistente, com log estruturado.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
import structlog

log = structlog.get_logger("marenostrum.errors")


class DomainError(Exception):
    """Base de erros previstos do dominio."""
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "domain_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class UnauthorizedError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_handler(_: Request, exc: DomainError):
        log.warning("domain_error", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db_handler(_: Request, exc: SQLAlchemyError):
        # Nao expor detalhes internos do banco ao cliente
        log.error("db_error", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "db_error", "message": "Erro interno no servidor"},
        )
