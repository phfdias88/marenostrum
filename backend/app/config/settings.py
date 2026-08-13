"""
Configuracao centralizada (Pydantic Settings).
Le variaveis de ambiente / .env com tipagem estatica.
"""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_NAME: str = "MareNostrum API"

    # Postgres
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "marenostrum"
    POSTGRES_USER: str = "marenostrum"
    POSTGRES_PASSWORD: str = "changeme"

    # JWT
    JWT_SECRET_KEY: str = Field(..., min_length=16)
    JWT_ALGORITHM: str = "HS256"
    # 7 dias — ferramenta de campanha de uso diário; evita logout no meio do uso.
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # ---- Deploy sob subdiretório (basePath) --------------------------------
    # Quando o SaaS é servido num subpath do domínio do cliente (ex.:
    # marenostrumconsult.com.br/sistema) atrás de um proxy reverso.
    # VAZIO = servido na raiz (comportamento atual em srv1412083.hstgr.cloud).
    #
    # ROOT_PATH é o PREFIXO PÚBLICO até a app (NÃO inclui o /api interno: os
    # routers desta app já registram sob /api). Com o nginx tirando o /sistema
    # antes de chegar no container, o FastAPI recebe /api/... nativamente e o
    # root_path só serve pra Swagger/OpenAPI gerarem URLs com o /sistema certo.
    # Ex.: "/sistema" → docs em /sistema/api/docs, "Try it out" acerta as rotas.
    ROOT_PATH: str = ""

    # Base pública usada em links absolutos gerados pelo backend (rodapé + QR
    # code do dossiê PDF). DEVE incluir o basePath quando houver.
    # Ex.: "https://marenostrumconsult.com.br/sistema".
    PUBLIC_URL_BASE: str = "https://srv1412083.hstgr.cloud"

    # Webhook fallback global. Usado quando o tenant NAO tem webhook_secret
    # proprio (typicamente em dev/staging). Em producao, prefira sempre
    # secret per-tenant — vazamento do global = todos os tenants caem.
    WEBHOOK_GLOBAL_SECRET: str | None = None

    # Google Calendar (read-only) — opcional. Vazio = integração desligada.
    # Crie 1 credencial OAuth no Google Cloud Console (uma vez, na conta do app).
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    # URI de callback REGISTRADA no Google (precisa bater exatamente).
    GOOGLE_REDIRECT_URI: str | None = None

    # Geocoding (Nominatim/OpenStreetMap)
    # User-Agent obrigatorio pela politica de uso do Nominatim.
    # Use o email do projeto para contato em caso de uso abusivo.
    NOMINATIM_USER_AGENT: str = "MareNostrum/0.1 (admin@marenostrum.local)"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    # Cidade/UF default usada quando o contato nao informar — base do MVP
    GEOCODING_DEFAULT_CITY: str = "Juiz de Fora"
    GEOCODING_DEFAULT_STATE: str = "MG"

    # ---- Billing (Asaas) — assinatura recorrente do B.I. Eleitoral Completo ----
    # Vazio = billing DESLIGADO (dev/staging/enquanto não migra). A chave é de
    # PRODUÇÃO ($aact_prod_) ou sandbox ($aact_hmlg_) e vive SÓ no .env do VPS —
    # NUNCA no código/git/chat. base_url é derivada de ASAAS_ENV (chave e base
    # têm que ser do mesmo ambiente, senão 401).
    ASAAS_API_KEY: str | None = None
    ASAAS_ENV: str = "production"  # production | sandbox
    # authToken estático do webhook (comparado com o header asaas-access-token).
    # Gerado por nós, NUNCA igual à API key.
    ASAAS_WEBHOOK_TOKEN: str | None = None
    # User-Agent é header OBRIGATÓRIO na API do Asaas (contas pós-11/06/2024).
    ASAAS_USER_AGENT: str = "MareNostrum/1.0"
    # Plano vendido — o preço é fonte da verdade AQUI (não confiar no valor que
    # vem do cliente no checkout).
    BILLING_PLAN_NAME: str = "B.I. Eleitoral Completo"
    BILLING_PLAN_SLUG: str = "bi_eleitoral_completo"
    BILLING_PLAN_VALUE: float = 250.00
    BILLING_PLAN_CYCLE: str = "MONTHLY"
    # Dias de tolerância após o vencimento antes de suspender o acesso.
    BILLING_GRACE_DAYS: int = 5

    # ---- E-mail transacional (SMTP do domínio) — entrega do link de senha -----
    # Vazio = envio DESLIGADO: o serviço apenas LOGA o link (dev). Preencher com
    # o SMTP do domínio (@marenostrumconsult) no go-live.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    # Remetente exibido, ex.: "MareNostrum <acesso@marenostrumconsult.com.br>".
    SMTP_FROM: str | None = None
    SMTP_STARTTLS: bool = True

    @property
    def asaas_base_url(self) -> str:
        return (
            "https://api.asaas.com/v3"
            if self.ASAAS_ENV == "production"
            else "https://api-sandbox.asaas.com/v3"
        )

    @property
    def database_url(self) -> str:
        # psycopg v3 driver
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cache para evitar releitura do .env em cada request."""
    return Settings()  # type: ignore[call-arg]
