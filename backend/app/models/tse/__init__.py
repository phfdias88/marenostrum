"""
Modelos TSE — dados PÚBLICOS oficiais do Tribunal Superior Eleitoral.

IMPORTANTE: estas tabelas NÃO herdam TenantMixin.

Razão: dados TSE são públicos (https://dadosabertos.tse.jus.br/) e
compartilhados entre TODOS os tenants. Não faz sentido ter
"candidatos do tenant A vs tenant B" — todos veem o mesmo Lula, mesmo PT,
mesma eleição 2024.

Tenant isolation continua válido pra dados PRIVADOS do mandato/campanha:
  - contacts, demands, interactions, voting_places (CRM)

Tenant não-isolado pra dados PÚBLICOS:
  - elections, parties, candidates, municipalities, vote_results (TSE)
"""
from app.models.tse.candidate import Candidate
from app.models.tse.election import Election
from app.models.tse.municipality import Municipality
from app.models.tse.party import Party
from app.models.tse.section_vote import TseSectionVote
from app.models.tse.sync_job import TseSyncJob, SyncJobStatus
from app.models.tse.vote_result import VoteResult
from app.models.tse.voting_place import TseVotingPlace

__all__ = [
    "Election",
    "Party",
    "Candidate",
    "Municipality",
    "VoteResult",
    "TseSyncJob",
    "SyncJobStatus",
    "TseVotingPlace",
    "TseSectionVote",
]
