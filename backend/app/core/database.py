"""
Configuracao do SQLAlchemy + sessao por request.
Pool conservador para VPS pequena (10 conexoes max).
"""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# Pool conservador: a soma (pool_size + max_overflow) deve estar bem
# abaixo de max_connections do Postgres (50 no docker-compose).
engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,   # evita conexao morta apos idle
    pool_recycle=1800,    # recicla a cada 30min
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency basica de sessao. Use `get_tenant_db` em rotas autenticadas."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
