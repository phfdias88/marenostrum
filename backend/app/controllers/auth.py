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
    summary="Autenticar e receber JWT",
    description="""\
Emite um **JWT** vinculado ao tenant (`tid`) e ao usuário (`sub`).

### Fluxo
1. Informe `tenant_slug` (apelido único da campanha), `email` e `password`
2. Backend valida em **constant-time** (anti timing-attack)
3. Sucesso → retorna `access_token` válido por 60 minutos

### Erros
- **401** — credenciais inválidas. Mensagem **sempre genérica**
  (`"Credenciais invalidas"`), por design — anti user-enumeration.
  Não distinguimos "email errado" de "senha errada" nem de "tenant inexistente".

### Como usar o token retornado
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```
""",
    responses={
        200: {"description": "Login bem-sucedido"},
        401: {
            "description": "Credenciais inválidas (mensagem genérica)",
            "content": {"application/json": {"example": {
                "code": "unauthorized",
                "message": "Credenciais invalidas",
            }}},
        },
    },
)
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    return AuthService(db).login(payload)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Dados do usuário autenticado",
    description="""\
Retorna o **usuário** e **tenant** associados ao JWT enviado.

Útil para:
- Provar ponta-a-ponta que o JWT foi aceito
- Confirmar que o `tenant_id` do token bate com o registro no DB
- Exibir nome/role/avatar no header do frontend

### Defesa em profundidade
Mesmo com JWT válido (assinatura ok), o backend **re-valida no banco** que:
- O usuário ainda existe e está ativo
- O `tenant_id` do token bate com o `tenant_id` do usuário no DB

Isso protege contra tokens forjados com `tid` arbitrário.
""",
)
def me(ctx: CurrentTenant) -> MeResponse:
    return AuthService.me(ctx)
