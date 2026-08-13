"""
Tratamento de erros centralizado: exceptions de dominio + handlers FastAPI.
Toda excecao de dominio vira HTTP de forma consistente, com log estruturado.
"""
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
import structlog

log = structlog.get_logger("marenostrum.errors")

# Rótulos PT-BR de campos comuns, pra mensagens de validação legíveis.
_FIELD_LABELS = {
    "password": "senha",
    "new_password": "senha",
    "current_password": "senha atual",
    "email": "e-mail",
    "full_name": "nome",
    "name": "nome",
    "tenant_name": "nome da campanha",
    "tenant_slug": "identificador da campanha",
}


def _field_label(loc) -> str | None:
    """Extrai o rótulo PT do último campo do `loc` (ex: ('body','new_password'))."""
    for part in reversed(list(loc or [])):
        if isinstance(part, str) and part != "body":
            return _FIELD_LABELS.get(part, part.replace("_", " "))
    return None


def _friendly_validation_message(errors: list[dict]) -> str:
    """Converte o 1º erro de validação do Pydantic numa frase PT-BR clara —
    pra não exibir 'Erro no servidor (HTTP 422)' quando é só requisito de campo
    (ex: senha curta). NUNCA usa o valor digitado (evita vazar senha)."""
    if not errors:
        return "Dados inválidos. Revise os campos e tente novamente."
    e = errors[0]
    etype = str(e.get("type", ""))
    raw = str(e.get("msg", "")).strip()
    ctx = e.get("ctx") or {}
    label = _field_label(e.get("loc"))
    base = label.capitalize() if label else "O valor"

    if etype == "value_error":
        # ValueError de validador custom: Pydantic v2 prefixa com "Value error, ".
        for p in ("Value error, ", "Assertion failed, "):
            if raw.startswith(p):
                return raw[len(p):]
        return raw
    if etype == "missing":
        return (
            f"Preencha o campo obrigatório: {label}."
            if label else "Preencha todos os campos obrigatórios."
        )
    if etype == "string_too_short":
        n = ctx.get("min_length")
        return (
            f"{base} deve ter pelo menos {n} caracteres." if n
            else f"{base} está muito curto(a)."
        )
    if etype == "string_too_long":
        n = ctx.get("max_length")
        return (
            f"{base} deve ter no máximo {n} caracteres." if n
            else f"{base} está muito longo(a)."
        )
    if "email" in etype:
        return "E-mail inválido. Confira o endereço digitado."
    # Fallback: usa a msg do Pydantic (evita o genérico 'HTTP 422').
    return raw or "Dados inválidos. Revise os campos e tente novamente."


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


class AmbiguousLoginError(DomainError):
    """Mesmo e-mail+senha em mais de uma campanha: o usuário precisa escolher.
    Carrega as opções pra UI montar o seletor (código: choose_tenant)."""
    status_code = status.HTTP_409_CONFLICT
    code = "choose_tenant"

    def __init__(self, message: str, options: list[dict] | None = None):
        super().__init__(message)
        self.options = options or []


class TrialExpiredError(DomainError):
    """Acesso temporário (trial) esgotado. Código dedicado pra o frontend
    distinguir de outros 403 e mostrar a mensagem certa."""
    status_code = status.HTTP_403_FORBIDDEN
    code = "trial_expired"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_handler(_: Request, exc: DomainError):
        log.warning("domain_error", code=exc.code, message=exc.message)
        body = {"code": exc.code, "message": exc.message}
        # Erros que carregam dados extras pra UI (ex: escolher a campanha).
        extra = getattr(exc, "options", None)
        if extra:
            body["options"] = extra
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError):
        # Erros de validação do Pydantic (422): traduz pra 1 frase PT-BR clara
        # e responde no MESMO formato {code, message} dos demais erros — assim
        # o frontend mostra "A senha deve ter pelo menos 10 caracteres." em vez
        # de "Erro no servidor (HTTP 422)".
        # Logamos só os CAMPOS que falharam — NUNCA o valor (exc.errors() traz
        # 'input', que num campo de senha seria a própria senha).
        errors = exc.errors()
        log.info(
            "validation_error",
            fields=[e.get("loc") for e in errors],
            types=[e.get("type") for e in errors],
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "validation_error",
                "message": _friendly_validation_message(errors),
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db_handler(_: Request, exc: SQLAlchemyError):
        # Nao expor detalhes internos do banco ao cliente
        log.error("db_error", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "db_error", "message": "Erro interno no servidor"},
        )
