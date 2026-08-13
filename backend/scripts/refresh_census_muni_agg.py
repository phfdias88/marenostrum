"""
Recalcula census_muni_agg (agregados municipais do censo materializados).

RODAR APÓS QUALQUER INGEST DE CENSO (setores novos/atualizados) — o
/census/uf-overview lê desta tabela; sem refresh, os agregados ficam do
ingest anterior. Mesmo SQL da migration 058 (fonte única lá).

Uso (scripts/ não vai na imagem — cp + PYTHONPATH):
  docker compose cp backend/scripts/refresh_census_muni_agg.py api:/tmp/refresh_agg.py
  docker compose exec -T api sh -c 'PYTHONPATH=/app python /tmp/refresh_agg.py'
"""
import importlib.util
import sys
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionLocal


def _load_agg_select() -> str:
    """Importa o AGG_SELECT da migration 058 (fonte única do SQL)."""
    for base in ("/app/alembic/versions", str(Path(__file__).parent.parent / "alembic" / "versions")):
        p = Path(base) / "058_census_muni_agg.py"
        if p.exists():
            spec = importlib.util.spec_from_file_location("m058", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod.AGG_SELECT
    print("ERRO: migration 058 não encontrada (o SQL vive lá).")
    sys.exit(1)


def main() -> None:
    agg = _load_agg_select()
    db = SessionLocal()
    try:
        db.execute(text("SET statement_timeout = 0"))  # agregação pesada
        db.execute(text("TRUNCATE census_muni_agg"))
        db.execute(text(f"INSERT INTO census_muni_agg {agg}"))
        db.commit()
        n = db.execute(text("SELECT count(*) FROM census_muni_agg")).scalar_one()
        print(f"census_muni_agg atualizado: {n} municípios")
        print("LEMBRETE: limpar o cache nginx do censo + bump CENSUS_V se o dado mudou.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
