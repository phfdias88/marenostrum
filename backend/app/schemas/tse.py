"""Schemas Pydantic pros endpoints TSE."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.tse import SyncJobStatus


class ElectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tse_code: int
    year: int
    round: int
    name: str
    type_name: str | None


class PartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: int
    abbreviation: str
    name: str


class MunicipalityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tse_code: int
    name: str
    state: str
    latitude: float | None = None
    longitude: float | None = None


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: int
    name: str
    urn_name: str
    office_code: int
    office_name: str
    state: str
    situation: str | None
    # Resultado da eleicao: ELEITO, ELEITO POR QP/MÉDIA, NÃO ELEITO,
    # SUPLENTE, 2º TURNO, etc. None se ainda nao backfilled.
    result_status: str | None = None
    # Enriquecimento (so preenchido no detalhe): patrimonio + redes sociais
    assets_total: float | None = None
    social_links: list[str] | None = None
    # Financas de campanha (prestacao de contas)
    revenue_total: float | None = None
    expense_total: float | None = None
    # Município com mais votos — só pra cargo municipal (prefeito/vereador);
    # pro card exibir "UF - MUNICÍPIO - ANO" em vez de só "UF - ANO".
    primary_municipality_name: str | None = None
    # Total de votos do candidato (pra exibir/ordenar na Análise por Partidos).
    total_votes: int | None = None
    # Quando a busca agrupa por pessoa (group_person): quantas candidaturas essa
    # pessoa tem (ex: Bolsonaro = 3). None na busca normal.
    candidacy_count: int | None = None
    party: PartyRead
    election: ElectionRead


class VoteResultByMunicipality(BaseModel):
    """Resultado de UM candidato em UM município (pra montar tabela)."""
    municipality: MunicipalityRead
    votes: int


class CandidateResultsResponse(BaseModel):
    """GET /candidates/{id}/results — votos do candidato por município."""
    candidate: CandidateRead
    results: list[VoteResultByMunicipality]
    total_votes: int
    municipalities_with_votes: int


class TopCandidateInMunicipality(BaseModel):
    """Linha da tabela 'top candidatos no municipio X'."""
    candidate: CandidateRead
    votes: int


class MunicipalityResultsResponse(BaseModel):
    """GET /municipalities/{id}/top-candidates — top votados num municipio."""
    municipality: MunicipalityRead
    results: list[TopCandidateInMunicipality]
    total_results: int
    # Soma de TODOS os votos nominais do cargo no municipio (denominador
    # pra calcular % de cada candidato). 0 se nao houver filtro de cargo.
    total_votes: int = 0
    office_code: int | None = None
    office_name: str | None = None
    # Ano da eleição mostrada (default = mais recente disponível). Evita
    # misturar candidaturas de anos diferentes (mesma pessoa aparecendo 2x).
    year: int | None = None


class CandidateByNeighborhoodItem(BaseModel):
    """Linha de votos por bairro: nome + total + locais agregados + centroide."""
    neighborhood: str
    votes: int
    places_count: int
    electors_total: int
    # Centroide aprox dos locais (media simples)
    avg_lat: float | None
    avg_lng: float | None
    # Cruzamento com o Censo IBGE 2022 (match por nome normalizado; presente
    # só onde o município tem dados censitários carregados). None = sem match.
    census_population: int | None = None
    census_households: int | None = None
    # votos ÷ eleitores aptos dos locais do bairro, em % (mesma base —
    # votos são contados ONDE se vota; moradores entram só como contexto).
    penetration_pct: float | None = None


class CandidateByNeighborhoodResponse(BaseModel):
    candidate: CandidateRead
    municipality: MunicipalityRead | None  # filtrado por municipio especifico
    items: list[CandidateByNeighborhoodItem]
    total_votes: int
    total_neighborhoods: int


class ElectionStatsResponse(BaseModel):
    """GET /elections/{id}/stats — sumario de uma eleicao."""
    election: ElectionRead
    candidates_count: int
    municipalities_count: int
    total_votes: int


class PartyPerformanceItem(BaseModel):
    """Desempenho de um partido: votos + eleitos + candidatos."""
    party: PartyRead
    total_votes: int
    elected_count: int
    candidates_count: int


class PartyEvolutionItem(BaseModel):
    """Desempenho de um partido numa eleição (ano), somando todos os cargos."""
    year: int
    elected_count: int
    candidates_count: int
    total_votes: int


class PartyEvolutionResponse(BaseModel):
    """Evolução do partido ao longo das eleições disponíveis (2014–2024)."""
    party: PartyRead
    items: list[PartyEvolutionItem]  # ordenado por ano asc


class WinnerMapPoint(BaseModel):
    """Municipio + partido/candidato vencedor (pra mapa colorido)."""
    municipality_id: UUID
    name: str
    state: str
    lat: float
    lng: float
    party_number: int
    party_abbreviation: str
    winner_name: str
    votes: int


class WinnersMapResponse(BaseModel):
    year: int
    office_code: int
    points: list[WinnerMapPoint]


class RankedCandidate(BaseModel):
    """Linha do ranking nacional: candidato + total de votos."""
    candidate: CandidateRead
    total_votes: int


class TopCandidatesResponse(BaseModel):
    year: int
    office_code: int | None
    office_name: str | None
    state: str | None
    items: list[RankedCandidate]


class PartyPerformanceResponse(BaseModel):
    """GET /stats/party-performance — ranking de partidos por votos/eleitos."""
    year: int
    office_code: int | None
    office_name: str | None
    state: str | None
    items: list[PartyPerformanceItem]
    total_votes: int
    total_elected: int


class SyncJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    dataset: str
    year: int
    status: SyncJobStatus
    started_at: datetime | None
    completed_at: datetime | None
    rows_processed: int
    rows_total: int | None
    candidates_imported: int
    parties_imported: int
    municipalities_imported: int
    vote_results_imported: int
    error_message: str | None
    created_at: datetime


class SyncJobCreated(BaseModel):
    job_id: UUID = Field(..., description="Use em GET /tse/sync/{id} pra acompanhar progresso")
    dataset: str
    status: SyncJobStatus


# ----------------------------------------- Radar de Oportunidades / Caminho


class OpportunityMunicipality(BaseModel):
    """Município no radar do candidato: eleitorado x votos = penetração."""
    municipality_id: UUID
    name: str
    state: str
    electorate: int            # eleitorado registrado (último ano disponível)
    votes: int                 # votos do candidato nesse município
    penetration_pct: float     # votos / eleitorado * 100
    available: int             # eleitorado - votos (eleitores "a conquistar")
    category: str              # "reduto" | "crescer" | "neutro"


class OpportunityResponse(BaseModel):
    """
    Radar de oportunidades do candidato:
    - redutos: onde tem maior penetração (consolidar)
    - crescer: maior eleitorado com baixa penetração (atacar)
    - resumo: eleitorado total alcançável + penetração média
    """
    candidate_id: UUID
    total_electorate_reached: int   # soma do eleitorado dos municípios com voto
    total_votes: int
    avg_penetration_pct: float
    strongholds: list[OpportunityMunicipality]   # redutos (top penetração)
    opportunities: list[OpportunityMunicipality]  # crescer (eleitorado x baixa penetração)


class PathTarget(BaseModel):
    """Município-alvo pra fechar o déficit de votos."""
    municipality_id: UUID
    name: str
    state: str
    available: int          # eleitorado - votos atuais (folga)
    suggested: int          # parcela do déficit sugerida (proporcional à folga)
    penetration_pct: float


class PathToVictoryResponse(BaseModel):
    """
    Caminho da vitória: quantos votos faltam pra vencer e onde buscá-los.
    Para cargos majoritários (presidente/governador/prefeito), compara com o
    vencedor da disputa. Para proporcionais, aponta a ferramenta de projeção.
    """
    candidate_id: UUID
    office_name: str
    scope: str               # "nacional" | "estadual" | "municipal" | "proporcional"
    candidate_votes: int
    is_winner: bool
    winner_name: str | None = None
    winner_votes: int = 0
    gap: int = 0             # votos pra ultrapassar o vencedor (0 se já vence)
    margin: int | None = None  # se vencedor, margem sobre o 2º
    available_electorate: int = 0
    targets: list[PathTarget] = []
    note: str | None = None


class AiReport(BaseModel):
    """Relatório estratégico gerado por IA (Gemini) sobre o candidato."""
    diagnostico: str
    score_viabilidade: int
    score_justificativa: str
    pontos_fortes: list[str]
    onde_crescer: list[str]
    narrativas: list[str]
    acoes_prioritarias: list[str]


class AiCompareReport(BaseModel):
    """Confronto estratégico entre dois candidatos gerado por IA (Maré IA)."""
    panorama: str
    quem_lidera: str
    minhas_vantagens: list[str]
    vantagens_adversario: list[str]
    onde_atacar: list[str]
    onde_defender: list[str]
    recomendacao_final: str
    # Números do confronto município a município (anexados pelo serviço)
    confronto: dict | None = None


class AiTerritoryReport(BaseModel):
    """Inteligência de Território (Maré IA): contatos da campanha × eleitorado
    × votos do adversário, por município/bairro. Análise PRIVADA do tenant."""
    panorama: str
    onde_tenho_base: list[str]
    onde_falta_cadastrar: list[str]
    onde_disputar_adversario: list[str]
    meta_cadastro: list[str]
    acoes_prioritarias: list[str]
    # Tabelas de números (anexadas pelo serviço pro frontend exibir).
    dados: dict | None = None


class ElectorateResponse(BaseModel):
    """Perfil do eleitorado de um município (gênero/idade/escolaridade/estado
    civil/raça)."""
    municipality: MunicipalityRead
    year: int
    total: int
    by_gender: dict[str, int]
    by_age: dict[str, int]
    by_education: dict[str, int]
    # Nullable: municípios importados antes do migration 043/re-import ficam sem.
    by_marital_status: dict[str, int] = {}
    by_race: dict[str, int] = {}


class ElectorateProfileResponse(BaseModel):
    """
    Perfil socioeconômico/demográfico do território do candidato.

    Cruza os votos do candidato por município com o perfil do eleitorado
    (gênero/idade/escolaridade do TSE) ponderado pelos votos — estima de que
    tipo de território vem a votação. Compara com a média do estado (baseline)
    pra mostrar onde o candidato é mais forte que a média (ex: "+8pp de jovens
    18-24 frente à média estadual").
    """
    candidate_id: UUID
    state: str
    municipalities_with_votes: int
    municipalities_covered: int   # com dado de eleitorado disponível
    coverage_pct: float           # % dos votos coberto por dado de perfil
    # Perfil do território do candidato (ponderado por voto), em %
    by_gender: dict[str, float]
    by_age: dict[str, float]
    by_education: dict[str, float]
    # Média do estado (todos os municípios da UF, por eleitorado), em %
    baseline_by_gender: dict[str, float]
    baseline_by_age: dict[str, float]
    baseline_by_education: dict[str, float]
    # Destaques: maiores desvios frente à média estadual
    highlights: list[str]


class ZoneVoteItem(BaseModel):
    zone: int
    municipality_name: str
    state: str
    votes: int


class CandidateZoneVotesResponse(BaseModel):
    """Votos de um candidato distribuídos por zona eleitoral."""
    candidate_id: UUID
    total_votes: int
    items: list[ZoneVoteItem]


class ZoneTopCandidate(BaseModel):
    candidate: CandidateRead
    votes: int


class MunicipalityZone(BaseModel):
    zone: int
    total_votes: int
    candidates: list[ZoneTopCandidate]


class MunicipalityZonesResponse(BaseModel):
    """Top candidatos por zona num município (cargo/ano)."""
    municipality: MunicipalityRead
    office_code: int | None = None
    office_name: str | None = None
    zones: list[MunicipalityZone]


# ---------- Timeline eleitoral do municipio ----------

class TimelineWinner(BaseModel):
    """Candidato vencedor num cargo/ano numa cidade."""
    candidate_id: UUID
    urn_name: str
    name: str
    party_abbr: str
    party_number: int
    party_name: str
    result_status: str | None
    votes: int


class TimelineItem(BaseModel):
    """Resultado de uma eleicao num cargo/ano na cidade."""
    year: int
    office_code: int
    office_name: str
    round: int = 1  # 1=1o turno, 2=2o turno (relevante pra Presidente/Governador)
    total_votes: int
    winner: TimelineWinner | None
    runner_up: TimelineWinner | None = None
    candidates_count: int


class MunicipalityTimelineResponse(BaseModel):
    municipality: MunicipalityRead
    items: list[TimelineItem]


# ----------------------------------------------------- Trajetória (histórico)


class TrajectoryItem(BaseModel):
    """Uma candidatura da mesma pessoa numa eleição (ano)."""
    candidate_id: UUID
    year: int
    office_code: int
    office_name: str
    state: str
    party_abbreviation: str
    party_number: int
    number: int
    total_votes: int | None = None
    result_status: str | None = None


class CandidateTrajectoryResponse(BaseModel):
    """
    Histórico eleitoral da mesma pessoa (match por nome civil completo),
    ordenado do mais recente pro mais antigo. `current_id` é o candidato
    consultado (pra destacar na UI).
    """
    name: str
    current_id: UUID
    items: list[TrajectoryItem]
