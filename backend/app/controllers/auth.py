"""Controller de autenticacao."""
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant
from app.schemas.auth import LoginRequest, MeResponse, TokenResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Autentica usuario e retorna JWT",
)
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    return AuthService(db).login(payload)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Dados do usuario logado (prova ponta-a-ponta do JWT + tenant)",
)
def me(ctx: CurrentTenant) -> MeResponse:
    return AuthService.me(ctx)
