"""Import central dos models (necessario para Alembic detectar metadata)."""
from app.models.base import Base
from app.models.contact import Contact, ContactType
from app.models.demand import Demand, DemandStatus
from app.models.interaction import Interaction
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.voting_place import VotingPlace

__all__ = [
    "Base",
    "Contact",
    "ContactType",
    "Demand",
    "DemandStatus",
    "Interaction",
    "Tenant",
    "User",
    "UserRole",
    "VotingPlace",
]
