# MareNostrum — Inteligência de Dados Eleitorais

> SaaS multi-tenant de inteligência política: dados oficiais do TSE + censo do IBGE +
> CRM de campanha + relatórios por IA, num único Super App.

Plataforma completa para campanhas eleitorais brasileiras. Cruza **dados eleitorais
oficiais** (Tribunal Superior Eleitoral), **dados socioeconômicos** (Censo IBGE 2022) e
um **CRM de relacionamento com eleitores**, entregando análises, mapas e projeções que
ajudam o candidato na tomada de decisão — tudo numa interface rápida e responsiva.

Projeto full-stack desenvolvido do zero: modelagem de dados, pipelines de ingestão,
API, frontend, infraestrutura e deploy em produção.

---

## ✨ Destaques técnicos

- **Ingestão de dados em escala** — importadores que baixam ZIPs de **2GB+** do TSE e
  arquivos de **136MB** do IBGE, parseados em *streaming* (`TextIOWrapper` sobre o zip)
  para nunca estourar a memória de uma VPS de 4GB.
- **454 mil candidatos · 5.571 municípios · 8,7M+ registros de votos · ~205 mil setores
  censitários** indexados e consultáveis.
- **Cache em 3 camadas** (browser → nginx com volume persistente → in-memory por
  processo) com *self-warming*: rotas quentes respondem em **0,1–0,4s** mesmo em
  consultas que varrem milhões de linhas.
- **Agregação censitária correta** — a "regra da sensibilidade": valores absolutos
  somam; médias e taxas são **média ponderada** `Σ(valor×peso)÷Σ(peso)`, centralizada
  numa única fonte de verdade (`censusAggregate.ts`).
- **Projeção de cadeiras** pelo método **D'Hondt** (quociente eleitoral + médias).
- **Relatórios estratégicos por IA** (Google Gemini) — perfil do território,
  oportunidades e comparativos candidato × adversário.
- **Dossiê PDF** do candidato gerado server-side (foto, patrimônio, votos por
  bairro/zona, mini-mapa, QR code).
- **Multi-tenant** com isolamento por `tenant_id` no JWT + dupla validação no banco;
  sessão com renovação deslizante; *feature-flags* por usuário.
- **Backup automático** do Postgres (cron + rotação + guarda de disco) e
  **observabilidade** com logs estruturados (`structlog`).

---

## 🧱 Arquitetura

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│   Next.js 14 │     │       nginx         │     │     FastAPI      │
│  App Router  │────▶│  TLS · cache edge   │────▶│   (1 worker)     │
│  React 18 TS │     │  censo 7d · TSE 5m  │     │   ORJSONResponse │
│  Tailwind    │     │  warmup listener    │     │   structlog      │
│  Leaflet     │◀────│  :8088 (self-warm)  │◀────│   agg_cache 4h   │
└──────────────┘     └─────────────────────┘     └────────┬─────────┘
                                                           │
                                                  ┌────────▼─────────┐
                                                  │  PostgreSQL 16   │
                                                  │  geometria JSONB │
                                                  │  pg_dump diário  │
                                                  └──────────────────┘
        Tudo orquestrado via Docker Compose · deploy em VPS Linux
```

---

## 🛠️ Stack

| Camada           | Tecnologias                                                              |
|------------------|-------------------------------------------------------------------------|
| **Backend**      | Python 3.12 · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · Alembic           |
| **Banco**        | PostgreSQL 16 (geometria em JSONB, sem PostGIS) · tuning para VPS pequena |
| **Frontend**     | Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS           |
| **Mapas/Dados**  | Leaflet / react-leaflet · Recharts · GeoJSON simplificado (Douglas-Peucker) |
| **Auth**         | JWT (HS256) · bcrypt + pré-hash SHA-256 · multi-tenant                   |
| **IA**           | Google Gemini (relatórios e insights estratégicos)                      |
| **PDF**          | ReportLab · pypdf                                                        |
| **Infra**        | Docker Compose · nginx (TLS Let's Encrypt, cache de borda) · cron        |

---

## 📊 Principais funcionalidades

**Inteligência eleitoral (TSE)**
- Busca global de candidatos, municípios e partidos
- Perfil rico do candidato (redes sociais, patrimônio, receitas/despesas)
- Votação por município, bairro e zona; mapas de calor geolocalizados
- Desempenho por partido, ranking nacional, comparações
- Mapa do Brasil colorido pelo partido vencedor de cada cidade
- Histórico de 2014 a 2024; projeção de votos (D'Hondt)

**Inteligência censitária (IBGE 2022)** — *módulo premium*
- Drill-down Estado → Município → Bairro/Distrito → Setor censitário
- Indicadores: população, domicílios, densidade, alfabetização, cor ou raça, % urbana
- Mapa coroplético com múltiplos indicadores e busca de bairros
- Cruzamento território × votos para encontrar oportunidades de campanha

**CRM de campanha**
- Contatos, demandas com prazo/status, agenda parlamentar geolocalizada
- Aniversariantes, templates de WhatsApp, tags e segmentação
- Onboarding guiado, gestão de equipe com papéis

---

## 🚀 Rodando localmente

> Requer Docker + Docker Compose.

```bash
# 1. Configurar variáveis de ambiente (a partir dos templates)
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
#   edite os valores: senha do Postgres, JWT_SECRET_KEY (openssl rand -hex 32), etc.

# 2. Subir o stack
docker compose up -d --build

# 3. Rodar as migrations
docker compose exec api alembic upgrade head

# Frontend → http://localhost:3000   ·   API/docs → http://localhost:8000/docs
```

A ingestão dos dados do TSE e do IBGE é feita por scripts dedicados em
`backend/scripts/` (parametrizados por UF / ano via variáveis de ambiente).

---

## 📁 Estrutura

```
backend/
  app/
    controllers/    # rotas FastAPI (tse, census, auth, monitored, ...)
    models/         # entidades SQLAlchemy
    schemas/        # contratos Pydantic
    services/       # regras de negócio
    utils/          # ingestão TSE, geração de PDF, warmup, relatórios IA
    core/           # database, security (JWT), dependências, multi-tenant
  alembic/          # migrations versionadas
  scripts/          # ingestão de dados, backup, validações de consistência
frontend/
  app/dashboard/    # páginas (App Router): análises, censo, CRM, mapa
  components/        # UI, mapas (Leaflet), busca global, gráficos
  lib/              # client de API, cache, agregação censitária, auth
nginx/              # config de borda (TLS, cache, warmup)
docs/               # documentação técnica
docker-compose.yml  # orquestração dos serviços
```

---

## 🔒 Notas

- Segredos **nunca** são versionados — apenas `.env.example` com placeholders.
- Repositório destinado a demonstração técnica (portfólio). O produto é comercial.

---

<p align="center"><sub>Desenvolvido por Paulo Dias · full-stack (Python · TypeScript · infra)</sub></p>
