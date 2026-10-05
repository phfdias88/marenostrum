"""api_keys: acesso programatico com chave, somente leitura

Revision ID: 063
Revises: 062
Create Date: 2026-08-26

POR QUE: hoje a unica forma de falar com a API e o login de humano (e-mail +
senha -> JWT de 7 dias). Pra integrar um BI ou uma planilha, alguem teria que
guardar a SENHA de um usuario e refazer login sozinho — e a revogacao so
existiria trocando essa senha, o que derrubaria a pessoa junto.

A chave resolve os tres problemas: nasce ligada a um tenant, e revogavel
sozinha e nunca da poder de escrita.

SEGURANCA:
- Guardamos o SHA-256 da chave, nunca ela. Vazou o banco, ninguem entra.
- `prefix` guarda so os primeiros caracteres, pra identificar a chave numa
  lista sem poder reconstrui-la.
- `expires_at` permite chave temporaria (parceiro, teste).
- `revoked_at` desliga na hora, sem apagar o historico de quem usou.
- `scopes` nasce so com leitura; a dependencia recusa metodo de escrita.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "063"
down_revision: Union[str, None] = "062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            created_by   uuid REFERENCES users(id) ON DELETE SET NULL,
            name         varchar(120) NOT NULL,
            key_hash     varchar(64)  NOT NULL,
            prefix       varchar(16)  NOT NULL,
            scopes       varchar(200) NOT NULL DEFAULT 'read',
            expires_at   timestamptz,
            revoked_at   timestamptz,
            last_used_at timestamptz,
            use_count    integer NOT NULL DEFAULT 0,
            created_at   timestamptz NOT NULL DEFAULT now()
        )
    """)
    # UNIQUE no hash: toda autenticacao busca por ele — e o caminho quente.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_api_keys_hash ON api_keys (key_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_api_keys_tenant ON api_keys (tenant_id)"
    )
    op.execute(
        "COMMENT ON TABLE api_keys IS "
        "'Chaves de acesso programatico (somente leitura). Guarda SHA-256, "
        "nunca a chave.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_keys")
