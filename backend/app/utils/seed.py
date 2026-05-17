"""
Bootstrap CLI: cria um tenant + usuario owner.
Onboarding de candidato e MANUAL (politico SaaS nao tem self-registration).

Uso (dentro do container API):
    docker compose exec api python -m app.utils.seed \\
        --tenant-slug demo \\
        --tenant-name "Candidato Demo" \\
        --email admin@demo.local \\
        --password 'Senha@Forte123' \\
        --name "Admin Demo"
"""
import argparse
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User, UserRole


def seed(
    *,
    tenant_slug: str,
    tenant_name: str,
    email: str,
    password: str,
    full_name: str,
) -> int:
    with SessionLocal() as db:
        # Tenant (idempotente)
        tenant = db.execute(
            select(Tenant).where(Tenant.slug == tenant_slug)
        ).scalar_one_or_none()

        if tenant is None:
            tenant = Tenant(name=tenant_name, slug=tenant_slug, is_active=True)
            db.add(tenant)
            db.flush()
            print(f"[OK] Tenant criado: {tenant.slug} (id={tenant.id})")
        else:
            print(f"[..] Tenant ja existia: {tenant.slug} (id={tenant.id})")

        # Owner (idempotente: unique por (tenant_id, email))
        owner = db.execute(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == email,
            )
        ).scalar_one_or_none()

        if owner is None:
            owner = User(
                tenant_id=tenant.id,
                email=email,
                full_name=full_name,
                hashed_password=hash_password(password),
                role=UserRole.OWNER,
                is_active=True,
            )
            db.add(owner)
            print(f"[OK] Owner criado: {email}")
        else:
            print(f"[..] Owner ja existia: {email} (senha NAO foi atualizada)")

        db.commit()
        return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bootstrap MareNostrum: tenant + owner")
    p.add_argument("--tenant-slug", required=True, help="ex: candidato-joao-2026")
    p.add_argument("--tenant-name", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True, help="senha em texto puro (sera hasheada)")
    p.add_argument("--name", required=True, help="nome completo do owner")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(
        seed(
            tenant_slug=args.tenant_slug,
            tenant_name=args.tenant_name,
            email=args.email,
            password=args.password,
            full_name=args.name,
        )
    )
