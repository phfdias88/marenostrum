"""Import central dos models (necessario para Alembic detectar metadata)."""
from app.models.base import Base
from app.models.contact import Contact, ContactType
from app.models.interaction import Interaction
from app.models.tenant import Tenant
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "Contact",
    "ContactType",
    "Interaction",
    "Tenant",
    "User",
    "UserRole",
]
