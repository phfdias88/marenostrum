"""Entrypoint da aplicacao FastAPI."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.utils.warmup import warm_up_cache


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Aquece agg_cache em background (não bloqueia readiness)
    task = asyncio.create_task(warm_up_cache())
    yield
    task.cancel()

from app.config import get_settings
from app.controllers import api_router
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging

# ============================================================ Metadata

_VERSION = "1.0.0"

# Tags com descricao — aparecem agrupadas no Swagger, na ORDEM declarada.
_TAGS_METADATA = [
    {
        "name": "system",
        "description": (
            "**Sistema.** Endpoints de saude e meta-informacao da API. "
            "Nao requerem autenticacao."
        ),
    },
    {
        "name": "auth",
        "description": (
            "**Autenticacao multi-tenant.** Login emite JWT com `tid` "
            "(tenant_id) e `sub` (user_id) que sao validados em todas as "
            "rotas autenticadas via `Authorization: Bearer <token>`."
        ),
    },
    {
        "name": "contacts",
        "description": (
            "**CRM** — eleitores, lideranças, apoiadores e doadores da "
            "campanha. CRUD completo, busca por nome, paginação, import CSV "
            "em lote, soft delete e georreferenciamento automático via "
            "Nominatim (OpenStreetMap)."
        ),
    },
    {
        "name": "demands",
        "description": (
            "**Demandas do gabinete** — pedidos da população ao mandato "
            "(saúde, infraestrutura, etc). Workflow: aberta → em_andamento "
            "→ resolvida (ou cancelada). Toda demanda está vinculada a um "
            "contato ATIVO do tenant."
        ),
    },
    {
        "name": "voting-places",
        "description": (
            "**Inteligência eleitoral (próprios).** Locais de votação com "
            "votos agregados pro candidato do tenant + heatmap normalizado. "
            "Import CSV em lote. `/heatmap` retorna pontos prontos pro "
            "Leaflet.heat."
        ),
    },
    {
        "name": "tse",
        "description": (
            "**Dados públicos do TSE** (não-tenant). Sincronização "
            "automática do portal `dadosabertos.tse.jus.br`. Busca de "
            "candidatos por UF/cargo/partido + resultado de votos por "
            "município. Base pras telas de Análise (estilo Politique)."
        ),
    },
    {
        "name": "webhooks",
        "description": (
            "**Integrações externas.** Endpoints PÚBLICOS autenticados por "
            "secret per-tenant (constant-time comparison). Recebem eventos "
            "do BotConversa (WhatsApp), Zenvia, etc. e os armazenam como "
            "`Interaction` na timeline do contato correspondente."
        ),
    },
]

_DESCRIPTION = """
**MareNostrum App** — SaaS multi-tenant para gestão de campanhas políticas e mandatos.

## Recursos principais

- 🔐 **Multi-tenant** — cada campanha tem dados 100% isolados (testado em 9 cenários)
- 👥 **CRM de eleitores** com import CSV em lote e georreferenciamento automático
- 📋 **Demandas do gabinete** com workflow de status
- 📡 **Webhooks BotConversa** com timeline de interações por contato
- 🗺️ **Mapa interativo** com pins geocodificados

## Autenticação

Todas as rotas (exceto `/auth/login`, `/system/*` e `/webhooks/*`) exigem JWT:

```
Authorization: Bearer <token>
```

Obtenha o token via `POST /auth/login`. Validade padrão: 60 minutos.

## Convenções

- Datas em **ISO 8601 UTC** (`2026-05-17T19:46:39.551Z`)
- IDs em **UUID v4**
- Paginação via `?limit=N&offset=N` retorna envelope `{items, total, limit, offset}`
- Erros HTTP: `{"code": "...", "message": "..."}`
"""


# ============================================================ Factory

def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    app = FastAPI(
        title="MareNostrum API",
        description=_DESCRIPTION,
        version=_VERSION,
        lifespan=_lifespan,
        openapi_tags=_TAGS_METADATA,
        contact={
            "name": "MareNostrum App",
            "email": "phfdias88@gmail.com",
        },
        license_info={"name": "Proprietary"},
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        # Swagger UI customizado — sem CSS externo
        swagger_ui_parameters={
            "docExpansion": "none",          # rotas colapsadas por default
            "defaultModelsExpandDepth": 1,
            "displayRequestDuration": True,  # mostra tempo de cada request
            "filter": True,                  # campo de busca
            "syntaxHighlight.theme": "monokai",
            "tryItOutEnabled": True,
            "persistAuthorization": True,    # mantem o JWT entre reloads
        },
    )

    # CORS — origens vem do .env
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")

    # ------------------------------------------------ system endpoints

    @app.get(
        "/api/health",
        tags=["system"],
        summary="Healthcheck simples",
        description="Retorna `{status: ok}` se a app subiu. Nao testa o DB.",
    )
    def health():
        return {"status": "ok"}

    @app.get(
        "/api/info",
        tags=["system"],
        summary="Meta-informacao da API",
        description=(
            "Versão, status, links para documentação. Útil para integradores "
            "e monitoramento externo."
        ),
    )
    def info():
        return {
            "name": "MareNostrum API",
            "version": _VERSION,
            "status": "operational",
            "now": datetime.now(timezone.utc).isoformat(),
            "docs": {
                "swagger": "/api/docs",
                "redoc": "/api/redoc",
                "openapi": "/api/openapi.json",
            },
            "endpoints": {
                "auth": "/api/v1/auth/login",
                "contacts": "/api/v1/contacts",
                "demands": "/api/v1/demands",
                "webhooks": "/api/v1/webhooks/botconversa/{tenant_id}",
            },
            "contact": "phfdias88@gmail.com",
        }

    @app.get("/api", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/api/", response_class=HTMLResponse, include_in_schema=False)
    def api_landing():
        """Landing page HTML — funciona com ou sem trailing slash."""
        return _LANDING_HTML

    return app


# ============================================================ Landing HTML

_LANDING_HTML = f"""\
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>MareNostrum API v{_VERSION}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      --bg:#0a2752; --card:#0f3568; --accent:#1e6fd9;
      --txt:#e7eef9; --muted:#9bb3d4; --border:#1d4280;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; min-height:100vh; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
      background:linear-gradient(135deg,var(--bg) 0%, #0a1f3f 100%); color:var(--txt);
      display:flex; align-items:center; justify-content:center; padding:2rem;
    }}
    .wrap {{ max-width:880px; width:100%; }}
    header {{ text-align:center; margin-bottom:2.5rem; }}
    .logo {{
      display:inline-flex; align-items:center; gap:.75rem;
      font-size:1.75rem; font-weight:600; letter-spacing:-.02em;
    }}
    .logo-mark {{
      width:42px; height:42px; border-radius:10px;
      background:linear-gradient(135deg,var(--accent),#0a4fa8);
      display:grid; place-items:center; font-weight:700;
    }}
    .badge {{
      display:inline-block; padding:.25rem .65rem; border-radius:999px;
      background:var(--accent); color:#fff; font-size:.75rem; font-weight:600;
      letter-spacing:.05em; margin-top:.5rem;
    }}
    h1 {{ margin:.5rem 0 .25rem; font-size:2rem; }}
    p.tagline {{ color:var(--muted); margin:0; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:1rem; }}
    .card {{
      background:var(--card); border:1px solid var(--border); border-radius:14px;
      padding:1.25rem; transition:transform .15s, border-color .15s;
    }}
    .card:hover {{ transform:translateY(-2px); border-color:var(--accent); }}
    .card h3 {{ margin:0 0 .35rem; font-size:1.05rem; display:flex; align-items:center; gap:.5rem; }}
    .card p {{ margin:0 0 .75rem; color:var(--muted); font-size:.875rem; line-height:1.5; }}
    .card a {{
      display:inline-block; color:var(--accent); text-decoration:none;
      font-size:.85rem; font-weight:500; border-bottom:1px solid transparent;
    }}
    .card a:hover {{ border-bottom-color:var(--accent); }}
    footer {{
      margin-top:2.5rem; text-align:center; color:var(--muted); font-size:.8rem;
    }}
    footer code {{ background:var(--card); padding:.1rem .4rem; border-radius:4px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="logo">
        <span class="logo-mark">M</span>
        <span>MareNostrum API</span>
      </div>
      <div class="badge">v{_VERSION} · operational</div>
      <h1>SaaS de campanhas políticas e mandatos</h1>
      <p class="tagline">Multi-tenant · CRM · Demandas · WhatsApp · Mapa</p>
    </header>

    <section class="grid">
      <div class="card">
        <h3>📘 Swagger UI</h3>
        <p>Documentação interativa com botão "Try it out" pra testar cada endpoint direto no navegador.</p>
        <a href="/api/docs">Abrir Swagger →</a>
      </div>
      <div class="card">
        <h3>📚 ReDoc</h3>
        <p>Documentação em formato leitura — melhor pra entender o modelo de dados e fluxos.</p>
        <a href="/api/redoc">Abrir ReDoc →</a>
      </div>
      <div class="card">
        <h3>💚 Health</h3>
        <p>Endpoint mínimo de healthcheck (sem dependência de DB).</p>
        <a href="/api/health">/api/health</a>
      </div>
      <div class="card">
        <h3>ℹ️ Info</h3>
        <p>Meta-informação da API: versão, status, endpoints principais.</p>
        <a href="/api/info">/api/info</a>
      </div>
      <div class="card">
        <h3>🎯 OpenAPI Schema</h3>
        <p>JSON spec da API (OpenAPI 3.1) — importe no Postman, Insomnia, etc.</p>
        <a href="/api/openapi.json">/api/openapi.json</a>
      </div>
      <div class="card">
        <h3>🚪 Login (UI)</h3>
        <p>Acesso à interface web do MareNostrum App pra usuários finais.</p>
        <a href="/login">/login</a>
      </div>
    </section>

    <footer>
      <p>API privada. Acesso por <code>Authorization: Bearer &lt;token&gt;</code> via <code>/api/v1/auth/login</code>.</p>
    </footer>
  </div>
</body>
</html>"""


app = create_app()
