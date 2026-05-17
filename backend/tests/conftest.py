"""
Configuracao da suite de testes do MareNostrum App.

DECISOES IMPORTANTES:

1. SQLite in-memory (StaticPool) — ~50ms por teste, sem dependencia de Docker.
   `models/base.py` foi adaptado pra usar `sqlalchemy.Uuid` (cross-DB) ao
   inves de `postgresql.UUID`. Migrations Alembic continuam PG-only.

2. Schema criado via `Base.metadata.create_all(engine)` — testes NAO rodam
   Alembic. Em prod, alembic roda no entrypoint do container.

3. Override de `get_db` em vez de mexer no engine global — isola test data
   do dev/prod sem efeitos colaterais.

4. Geocoding SEMPRE mockado nos testes (autouse) — testes nao podem bater
   no Nominatim real. Cada teste fica em ~50ms; chamar HTTP real seria 1s+.

5. Duas fixtures de tenant prontas — `client_a` e `client_b` — porque o
   teste central da suite e' isolamento entre tenants.
"""
from __future__ import annotations

# IMPORTANTE: estes env vars precisam ser setados ANTES de importar `app.*`
# porque `Settings` exige JWT_SECRET_KEY com min_length=16 no carregamento.
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-at-least-16-chars")
os.environ.setdefault("APP_ENV", "test")
# Postgres vars dummy — SQLite in-memory substitui pelo engine de teste
os.environ.setdefault("POSTGRES_PASSWORD", "test")

from typing import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Base, Tenant, User, UserRole


# ----------------------------------------------------------- DB fixtures


@pytest.fixture
def engine():
    """SQLite in-memory por teste — schema fresco, isolamento total."""
    engine = create_engine(
        "sqlite:///:memory:",
        # StaticPool + check_same_thread=False = mesma conexao compartilhada
        # entre threads (necessario pro TestClient + in-memory DB).
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    TestSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False,
    )
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine, db_session) -> Generator[TestClient, None, None]:
    """
    TestClient com `get_db` override apontando pro engine de teste.
    Cada request abre sua propria sessao (igual em prod), mas todas usam
    o MESMO engine SQLite in-memory que `db_session` (mesma StaticPool).
    """
    TestSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False,
    )

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ----------------------------------------------- Geocoding mock (autouse)


@pytest.fixture(autouse=True)
def _disable_geocoding(monkeypatch):
    """
    SEMPRE mockado: nenhum teste bate no Nominatim real.
    Retornar None = "nao encontrou" — o background task termina sem update.
    """
    async def fake_geocode(_query):
        return None
    monkeypatch.setattr("app.utils.geocoding.geocode", fake_geocode)


# ----------------------------------------------- Tenant/User fixtures


def _make_tenant_and_owner(
    db: Session,
    *,
    slug: str,
    name: str,
    email: str,
    password: str = "Senha@Forte123",
) -> tuple[Tenant, User]:
    tenant = Tenant(name=name, slug=slug, is_active=True)
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=email,
        full_name=f"Owner {slug}",
        hashed_password=hash_password(password),
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(tenant)
    db.refresh(user)
    return tenant, user


@pytest.fixture
def tenant_a(db_session) -> tuple[Tenant, User, str]:
    """Tenant A + owner + JWT pronto."""
    tenant, user = _make_tenant_and_owner(
        db_session, slug="alpha", name="Campanha Alpha",
        email="alpha@example.com",
    )
    token = create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role.value,
    )
    return tenant, user, token


@pytest.fixture
def tenant_b(db_session) -> tuple[Tenant, User, str]:
    """Tenant B + owner + JWT pronto. Usado pra testes de isolamento."""
    tenant, user = _make_tenant_and_owner(
        db_session, slug="bravo", name="Campanha Bravo",
        email="bravo@example.com",
    )
    token = create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role.value,
    )
    return tenant, user, token


@pytest.fixture
def auth_a(client, tenant_a):
    """Helper: client autenticado como tenant A. Retorna funcao request()."""
    _, _, token = tenant_a
    headers = {"Authorization": f"Bearer {token}"}

    class _AuthedClient:
        def __init__(self, client, headers):
            self._c = client
            self._h = headers

        def get(self, url, **kw):
            return self._c.get(url, headers={**self._h, **kw.pop("headers", {})}, **kw)

        def post(self, url, **kw):
            return self._c.post(url, headers={**self._h, **kw.pop("headers", {})}, **kw)

        def put(self, url, **kw):
            return self._c.put(url, headers={**self._h, **kw.pop("headers", {})}, **kw)

        def delete(self, url, **kw):
            return self._c.delete(url, headers={**self._h, **kw.pop("headers", {})}, **kw)

    return _AuthedClient(client, headers)


@pytest.fixture
def auth_b(client, tenant_b):
    """Helper analogo pro tenant B."""
    _, _, token = tenant_b
    headers = {"Authorization": f"Bearer {token}"}

    class _AuthedClient:
        def __init__(self, client, headers):
            self._c = client
            self._h = headers

        def get(self, url, **kw):
            return self._c.get(url, headers={**self._h, **kw.pop("headers", {})}, **kw)

        def post(self, url, **kw):
            return self._c.post(url, headers={**self._h, **kw.pop("headers", {})}, **kw)

        def put(self, url, **kw):
            return self._c.put(url, headers={**self._h, **kw.pop("headers", {})}, **kw)

        def delete(self, url, **kw):
            return self._c.delete(url, headers={**self._h, **kw.pop("headers", {})}, **kw)

    return _AuthedClient(client, headers)
