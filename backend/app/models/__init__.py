"""Import central dos models (necessario para Alembic detectar metadata)."""
from app.models.base import Base
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.census import (
    AreaPonderacao,
    CensusGeo,
    Municipio,
    RegionType,
    Setor,
)
from app.models.contact import Contact, ContactType
from app.models.demand import Demand, DemandStatus
from app.models.agenda_event import AgendaEvent
from app.models.interaction import Interaction
from app.models.message_template import MessageTemplate
from app.models.monitored_candidate import MonitoredCandidate
from app.models.subscription import BillingEvent, Subscription
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
    "ApiKey",
    "AuditLog",
    # Censo IBGE (dados publicos, multi-granularidade)
    "CensusGeo",
    "RegionType",
    "Setor",
    "Municipio",
    "AreaPonderacao",
    # CRM (multi-tenant)
    "Contact",
    "ContactType",
    "Demand",
    "DemandStatus",
    "AgendaEvent",
    "Interaction",
    "MessageTemplate",
    "MonitoredCandidate",
    "Subscription",
    "BillingEvent",
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
