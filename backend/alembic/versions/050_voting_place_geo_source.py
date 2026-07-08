"""voting_place geo_source — origem/precisão da coordenada do local de votação

Distingue de onde veio a coordenada de cada TseVotingPlace, o que habilita:
 (a) a lista de "Locais Não Mapeados" (geo_source='unmapped'), e
 (b) o pipeline de enriquecimento saber o que reprocessar (centroide/unmapped).

Valores: 'tse' (coord real do TSE) | 'centroid' (fallback no centro do município,
impreciso) | 'nominatim' (recuperado via ViaCEP→Nominatim) | 'unmapped' (sem
coordenada). Faz o backfill classificando os locais já importados.

Revision ID: 050
Revises: 049
"""
from typing import Sequence, Union

from alembic import op

revision: str = "050"
down_revision: Union[str, None] = "049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tse_voting_places ADD COLUMN IF NOT EXISTS geo_source varchar(12)")
    # Backfill dos já existentes:
    # 1) sem coordenada = unmapped
    op.execute(
        "UPDATE tse_voting_places SET geo_source='unmapped' "
        "WHERE latitude IS NULL OR longitude IS NULL"
    )
    # 2) coordenada IDÊNTICA ao centroide do município = fallback (impreciso).
    #    O ingest gravava exatamente muni.latitude/longitude nesse caso.
    op.execute(
        "UPDATE tse_voting_places v SET geo_source='centroid' "
        "FROM tse_municipalities m "
        "WHERE v.municipality_id=m.id AND v.geo_source IS NULL "
        "  AND m.latitude IS NOT NULL AND m.longitude IS NOT NULL "
        "  AND v.latitude=m.latitude AND v.longitude=m.longitude"
    )
    # 3) o resto (coord real distinta) = tse
    op.execute(
        "UPDATE tse_voting_places SET geo_source='tse' "
        "WHERE geo_source IS NULL AND latitude IS NOT NULL"
    )
    # Índice pra listar não-mapeados/centroide por município rapidamente.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_vp_geo_source "
        "ON tse_voting_places (municipality_id, geo_source)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_vp_geo_source")
    op.execute("ALTER TABLE tse_voting_places DROP COLUMN IF EXISTS geo_source")
