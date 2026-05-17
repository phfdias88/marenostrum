"""Import central dos models (necessario para Alembic detectar metadata)."""
from app.models.base import Base
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.contact import Contact, ContactType

__all__ = [
    "Base",
    "Tenant",
    "User",
    "UserRole",
    "Contact",
    "ContactType",
]
