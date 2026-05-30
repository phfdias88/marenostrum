"""Import central dos models (necessario para Alembic detectar metadata)."""
from app.models.base import Base
from app.models.contact import Contact, ContactType
from app.models.demand import Demand, DemandStatus
from app.models.interaction import Interaction
from app.models.monitored_candidate import MonitoredCandidate
from app.models.tenant import Tenant
from app.models.tse import (
    Candidate,
    Election,
    Municipality,
    Party,
    SyncJobStatus,
    TseSyncJob,
    VoteResult,
)
from app.models.user import User, UserRole
from app.models.voting_place import VotingPlace

__all__ = [
    "Base",
    # CRM (multi-tenant)
    "Contact",
    "ContactType",
    "Demand",
    "DemandStatus",
    "Interaction",
    "MonitoredCandidate",
    "Tenant",
    "User",
    "UserRole",
    "VotingPlace",
    # TSE (dados publicos compartilhados)
    "Candidate",
    "Election",
    "Municipality",
    "Party",
    "SyncJobStatus",
    "TseSyncJob",
    "VoteResult",
]
