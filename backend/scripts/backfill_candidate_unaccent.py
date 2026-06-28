"""
Preenche tse_candidates.name_unaccent/urn_unaccent (existentes) e cria os índices
GIN trgm nessas colunas (CONCURRENTLY, sem lock). Roda 1x após a migration 048.

docker compose exec -d api sh -c 'PYTHONPATH=/app python /tmp/bf_unaccent.py > /tmp/bf_unaccent.log 2>&1'
"""
from sqlalchemy import text
from app.core.database import SessionLocal


def main() -> None:
    # 1. Backfill em lotes de 50k (evita transação/lock gigante).
    with SessionLocal() as db:
        db.execute(text("SET statement_timeout = 0"))
        pend = db.execute(
            text("SELECT count(*) FROM tse_candidates WHERE name_unaccent IS NULL")
        ).scalar() or 0
    print(f"a preencher: {pend}", flush=True)
    done = 0
    while True:
        with SessionLocal() as db:
            db.execute(text("SET statement_timeout = 0"))
            n = db.execute(text(
                "UPDATE tse_candidates SET "
                "name_unaccent = lower(f_unaccent(name)), "
                "urn_unaccent = lower(f_unaccent(urn_name)) "
                "WHERE id IN (SELECT id FROM tse_candidates "
                "WHERE name_unaccent IS NULL LIMIT 50000)"
            )).rowcount
            db.commit()
        done += n
        print(f"  backfill {done}", flush=True)
        if not n:
            break

    # 2. Índices GIN trgm nas colunas (CONCURRENTLY — fora de transação).
    bind = SessionLocal().get_bind()
    with bind.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("SET statement_timeout = 0"))
        for sql in (
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tse_cand_name_unacc_trgm "
            "ON tse_candidates USING gin (name_unaccent gin_trgm_ops)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tse_cand_urn_unacc_trgm "
            "ON tse_candidates USING gin (urn_unaccent gin_trgm_ops)",
        ):
            print("idx:", sql[:55], flush=True)
            conn.execute(text(sql))
    print("UNACCENT DONE", flush=True)


if __name__ == "__main__":
    main()
