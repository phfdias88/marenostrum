"""
Controller de webhooks externos.

ESTE ROUTER É PÚBLICO — NÃO usa CurrentTenant (JWT).
Autenticação via secret comparado em constant-time no service.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.webhook import WebhookAck, WebhookPayload
from app.services.webhook import WebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/botconversa/{tenant_id}",
    response_model=WebhookAck,
    summary="Receber evento do BotConversa (WhatsApp)",
    description="""\
Endpoint **público** (sem JWT) que recebe eventos do BotConversa e os armazena
como `Interaction` na timeline do contato correspondente.

### Autenticação por secret
O `tenant_id` está na URL pra identificar **qual** tenant é o destinatário.
Pra provar autenticidade, envie o `webhook_secret` configurado pra esse tenant:

- **Preferido**: header `X-Webhook-Secret: <secret>`
- **Fallback**: query string `?secret=<secret>`
  ⚠️ Query string aparece em logs do nginx/proxies — só use se o provedor
  não permitir custom header.

Comparação **constant-time** (`hmac.compare_digest`) — anti timing-attack.

### Tolerância de payload
Aceita **qualquer JSON** (`dict[str, Any]`). Helpers internos tentam extrair
campos em várias chaves comuns:

| Campo extraído | Chaves procuradas |
|---|---|
| `phone` | `phone`, `subscriber_phone`, `telefone`, `whatsapp`, `from` (+ nested em `subscriber`/`contact`) |
| `event_type` | `event`, `event_type`, `type`, `action` |
| `external_event_id` | `event_id`, `id`, `uuid`, `message_id` |

### Linkagem inteligente
1. Se `phone` extraído **bate** com contato ativo do tenant → vincula (`contact_matched: true`)
2. Se **não bate** → salva órfã (`contact_id: null`, mas `phone` preservado)
3. Pra relinkar órfãs depois, basta fazer `UPDATE` em batch

### Códigos de resposta
- **200** — evento aceito (mesmo se órfã!). NUNCA retornamos 4xx/5xx em
  payload ruim — webhook que falha = provedor reenvia = duplicatas
- **401** — secret ausente, errado, ou tenant sem `webhook_secret` configurado
- **404** — tenant não existe ou está inativo (mensagem genérica anti-enumeration)

### Como configurar pra um tenant
```sql
UPDATE tenants SET webhook_secret = '<random_64_chars>' WHERE id = '...';
```

Daí cole no painel do BotConversa:
```
URL: http://<host>/api/v1/webhooks/botconversa/<tenant_id>
Header: X-Webhook-Secret: <random_64_chars>
```
""",
)
def receive_botconversa_event(
    tenant_id: UUID,
    payload: Annotated[
        WebhookPayload,
        Body(
            ...,
            examples=[{
                "event": "mensagem_recebida",
                "id": "evt_abc123",
                "phone": "(32) 99999-1234",
                "message": {"text": "Oi, quero apoiar a campanha"},
                "subscriber": {"name": "João Silva"},
            }],
        ),
    ],
    db: Annotated[Session, Depends(get_db)],
    x_webhook_secret: Annotated[
        str | None,
        Header(
            alias="X-Webhook-Secret",
            description="Secret do tenant. Preferido (não vaza em logs).",
        ),
    ] = None,
    secret_query: Annotated[
        str | None,
        Query(
            alias="secret",
            description="Fallback do secret via query string. Vaza em logs — só pra dev.",
        ),
    ] = None,
) -> WebhookAck:
    secret = x_webhook_secret or secret_query
    return WebhookService(db).process_botconversa_event(
        tenant_id=tenant_id,
        secret_provided=secret,
        payload=payload,
    )
