/** Tipos espelhando os schemas Pydantic do backend. */

export type ContactType = "voter" | "leader" | "supporter" | "donor" | "other";

export type Contact = {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  whatsapp: string | null;
  instagram: string | null;
  facebook: string | null;
  cep: string | null;
  address: string | null;
  neighborhood: string | null;
  city: string | null;
  state: string | null;
  voting_place: string | null;
  latitude: number | null;
  longitude: number | null;
  birth_date: string | null; // ISO date "YYYY-MM-DD"
  type: ContactType;
  notes: string | null;
  /** Tags livres pra segmentação. Lowercase + slug ([a-z0-9_-], max 32). */
  tags: string[];
  /** Quem cadastrou (liderança/membro) — null em contatos antigos. */
  created_by_user_id: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
};

/** Quem já cadastrou contato (resposta de GET /v1/contacts/creators). */
export type ContactCreator = { id: string; name: string };

/** Tag + contagem (resposta de GET /v1/contacts/tags). */
export type ContactTag = { tag: string; count: number };

/** Template de mensagem WhatsApp (resposta de /v1/templates). */
export type MessageTemplate = {
  id: string;
  title: string;
  body: string;
  category: string | null;
  created_at: string;
  updated_at: string;
};

/** Evento da agenda parlamentar/campanha (resposta de /v1/agenda). */
export type AgendaEvent = {
  id: string;
  title: string;
  description: string | null;
  starts_at: string; // ISO datetime
  location_name: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  category: string | null;
  created_at: string;
  updated_at: string;
};

/** Aniversariante (resposta de GET /v1/contacts/birthdays). */
export type BirthdayContact = {
  id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  birth_date: string; // ISO "YYYY-MM-DD"
  days_until: number; // 0 = hoje
  age_turning: number | null;
  tags: string[];
};

/** Candidato monitorado (meu candidato / adversário) */
export type MonitoredCandidateRead = {
  id: string;
  candidate_id: string;
  label: string | null;
  is_mine: boolean;
  color: string | null;
  notes: string | null;
  created_at: string;
  candidate_found: boolean;
  candidate_name: string | null;
  candidate_number: number | null;
  candidate_party_abbr: string | null;
  candidate_office_name: string | null;
  candidate_state: string | null;
  candidate_municipality_name: string | null;
  candidate_total_votes: number | null;
  candidate_was_elected: boolean | null;
};

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export const CONTACT_TYPE_LABELS: Record<ContactType, string> = {
  voter: "Eleitor",
  leader: "Liderança",
  supporter: "Apoiador",
  donor: "Doador",
  other: "Outro",
};

/** Resposta de POST /contacts/import (espelha schema Pydantic do backend) */
export type ImportRowError = { row: number; message: string };

export type ImportResult = {
  imported: number;
  skipped: number;
  total_rows: number;
  errors: ImportRowError[];
};

// ----------------------------------------------------------------- Demand


export type DemandStatus = "aberta" | "em_andamento" | "resolvida" | "cancelada";

export const DEMAND_STATUS_LABELS: Record<DemandStatus, string> = {
  aberta: "Aberta",
  em_andamento: "Em andamento",
  resolvida: "Resolvida",
  cancelada: "Cancelada",
};

/** Variantes de Badge por status (mapeia pra badgeVariants em components/ui/badge.tsx) */
export const DEMAND_STATUS_BADGE: Record<
  DemandStatus,
  "amber" | "blue" | "emerald" | "slate"
> = {
  aberta: "amber",
  em_andamento: "blue",
  resolvida: "emerald",
  cancelada: "slate",
};

export type DemandContactSummary = {
  id: string;
  full_name: string;
};

export type Demand = {
  id: string;
  contact: DemandContactSummary;
  title: string;
  description: string;
  status: DemandStatus;
  category: string;
  created_at: string;
  updated_at: string;
};


// --------------------------------------------------------- VotingPlace


export type VotingPlace = {
  id: string;
  name: string;
  address: string | null;
  neighborhood: string | null;
  city: string | null;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  votes: number;
  total_voters: number | null;
  election_year: number | null;
  tse_code: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type HeatmapPoint = {
  lat: number;
  lng: number;
  intensity: number; // 0..1
  votes: number;
  name: string;
};

export type HeatmapResponse = {
  points: HeatmapPoint[];
  total_places: number;
  total_votes: number;
  max_votes: number;
};


// ----------------------------------------------------------------- TSE

export type TseParty = {
  id: string;
  number: number;
  abbreviation: string;
  name: string;
};

export type TseElection = {
  id: string;
  tse_code: number;
  year: number;
  round: number;
  name: string;
  type_name: string | null;
};

export type TseMunicipality = {
  id: string;
  tse_code: number;
  name: string;
  state: string;
  latitude: number | null;
  longitude: number | null;
};

export type TseCandidate = {
  id: string;
  number: number;
  name: string;
  urn_name: string;
  office_code: number;
  office_name: string;
  state: string;
  situation: string | null;
  result_status: string | null; // ELEITO, NÃO ELEITO, SUPLENTE, 2º TURNO...
  assets_total: number | null; // patrimônio declarado (R$)
  social_links: string[] | null; // URLs de redes sociais
  revenue_total: number | null; // receita de campanha (R$)
  expense_total: number | null; // despesa de campanha (R$)
  party: TseParty;
  election: TseElection;
};

/** Classifica o DS_SIT_TOT_TURNO do TSE numa categoria visual. */
export type ElectionOutcome = "elected" | "runoff" | "alternate" | "not_elected" | "unknown";

export function classifyResult(status: string | null): ElectionOutcome {
  if (!status) return "unknown";
  const s = status.toUpperCase();
  if (s.includes("2º TURNO") || s.includes("2O TURNO") || s.includes("SEGUNDO TURNO"))
    return "runoff";
  if (s.includes("SUPLENTE")) return "alternate";
  if (s.includes("NÃO ELEITO") || s.includes("NAO ELEITO")) return "not_elected";
  if (s.includes("ELEITO")) return "elected"; // ELEITO, ELEITO POR QP, POR MÉDIA
  return "unknown";
}

export const OUTCOME_LABEL: Record<ElectionOutcome, string> = {
  elected: "Eleito",
  runoff: "2º turno",
  alternate: "Suplente",
  not_elected: "Não eleito",
  unknown: "—",
};

export type TseVoteResultByMunicipality = {
  municipality: TseMunicipality;
  votes: number;
};

export type TseCandidateResults = {
  candidate: TseCandidate;
  results: TseVoteResultByMunicipality[];
  total_votes: number;
  municipalities_with_votes: number;
};

/** Trajetória eleitoral — mesma pessoa em várias eleições (2014–2024). */
export type TseTrajectoryItem = {
  candidate_id: string;
  year: number;
  office_code: number;
  office_name: string;
  state: string;
  party_abbreviation: string;
  party_number: number;
  number: number;
  total_votes: number | null;
  result_status: string | null;
};

export type TseCandidateTrajectory = {
  name: string;
  current_id: string;
  items: TseTrajectoryItem[];
};

/** Radar de oportunidades — eleitorado x votos por município. */
export type TseOpportunityMunicipality = {
  municipality_id: string;
  name: string;
  state: string;
  electorate: number;
  votes: number;
  penetration_pct: number;
  available: number;
  category: "reduto" | "crescer" | "neutro";
};

export type TseOpportunityResponse = {
  candidate_id: string;
  total_electorate_reached: number;
  total_votes: number;
  avg_penetration_pct: number;
  strongholds: TseOpportunityMunicipality[];
  opportunities: TseOpportunityMunicipality[];
};

/** Perfil socioeconômico/demográfico do território do candidato. */
export type TseElectorateProfile = {
  candidate_id: string;
  state: string;
  municipalities_with_votes: number;
  municipalities_covered: number;
  coverage_pct: number;
  by_gender: Record<string, number>;
  by_age: Record<string, number>;
  by_education: Record<string, number>;
  baseline_by_gender: Record<string, number>;
  baseline_by_age: Record<string, number>;
  baseline_by_education: Record<string, number>;
  highlights: string[];
};

/** Caminho da vitória: déficit de votos e onde buscá-los. */
export type TsePathTarget = {
  municipality_id: string;
  name: string;
  state: string;
  available: number;
  suggested: number;
  penetration_pct: number;
};

export type TsePathToVictory = {
  candidate_id: string;
  office_name: string;
  scope: "nacional" | "estadual" | "municipal" | "proporcional";
  candidate_votes: number;
  is_winner: boolean;
  winner_name: string | null;
  winner_votes: number;
  gap: number;
  margin: number | null;
  available_electorate: number;
  targets: TsePathTarget[];
  note: string | null;
};

/** Confronto estratégico por IA entre candidato e adversário (Maré IA). */
export type TseAiCompareH2HItem = {
  municipio: string;
  voce: number;
  adversario: number;
  vantagem?: number;
  desvantagem?: number;
};

export type TseAiCompare = {
  panorama: string;
  quem_lidera: string;
  minhas_vantagens: string[];
  vantagens_adversario: string[];
  onde_atacar: string[];
  onde_defender: string[];
  recomendacao_final: string;
  confronto?: {
    municipios_disputados: number;
    a_lidera_em: TseAiCompareH2HItem[];
    adversario_lidera_em: TseAiCompareH2HItem[];
  } | null;
};

/** Relatório estratégico gerado por IA (Gemini) sobre o candidato. */
export type TseAiReport = {
  diagnostico: string;
  score_viabilidade: number;
  score_justificativa: string;
  pontos_fortes: string[];
  onde_crescer: string[];
  narrativas: string[];
  acoes_prioritarias: string[];
};

/** Evolução do partido por eleição (2014–2024). */
export type TsePartyEvolutionItem = {
  year: number;
  elected_count: number;
  candidates_count: number;
  total_votes: number;
};

export type TsePartyEvolution = {
  party: TseParty;
  items: TsePartyEvolutionItem[];
};

export type TseTopCandidateInMunicipality = {
  candidate: TseCandidate;
  votes: number;
};

export type TseMunicipalityResults = {
  municipality: TseMunicipality;
  results: TseTopCandidateInMunicipality[];
  total_results: number;
  total_votes: number;
  office_code: number | null;
  office_name: string | null;
  year: number | null;
};

export type TseElectorate = {
  municipality: TseMunicipality;
  year: number;
  total: number;
  by_gender: Record<string, number>;
  by_age: Record<string, number>;
  by_education: Record<string, number>;
};

export type TseZoneVoteItem = {
  zone: number;
  municipality_name: string;
  state: string;
  votes: number;
};

export type TseZoneTopCandidate = { candidate: TseCandidate; votes: number };

export type TseMunicipalityZone = {
  zone: number;
  total_votes: number;
  candidates: TseZoneTopCandidate[];
};

export type TseMunicipalityZones = {
  municipality: TseMunicipality;
  office_code: number | null;
  office_name: string | null;
  zones: TseMunicipalityZone[];
};

// ---------- Timeline eleitoral do município ----------

export type TseTimelineWinner = {
  candidate_id: string;
  urn_name: string;
  name: string;
  party_abbr: string;
  party_number: number;
  party_name: string;
  result_status: string | null;
  votes: number;
};

export type TseTimelineItem = {
  year: number;
  office_code: number;
  office_name: string;
  round?: number; // 1=1º turno, 2=2º turno
  total_votes: number;
  winner: TseTimelineWinner | null;
  runner_up: TseTimelineWinner | null;
  candidates_count: number;
};

export type TseMunicipalityTimeline = {
  municipality: TseMunicipality;
  items: TseTimelineItem[];
};

export type TseCandidateZoneVotes = {
  candidate_id: string;
  total_votes: number;
  items: TseZoneVoteItem[];
};

export type TseCandidateByNeighborhoodItem = {
  neighborhood: string;
  votes: number;
  places_count: number;
  electors_total: number;
  avg_lat: number | null;
  avg_lng: number | null;
  // Cruzamento Censo IBGE 2022 (null = município sem censo ou bairro sem match)
  census_population?: number | null;
  census_households?: number | null;
  penetration_pct?: number | null;
};

export type TseCandidateByNeighborhoodResponse = {
  candidate: TseCandidate;
  municipality: TseMunicipality | null;
  items: TseCandidateByNeighborhoodItem[];
  total_votes: number;
  total_neighborhoods: number;
};

export type TseWinnerMapPoint = {
  municipality_id: string;
  name: string;
  state: string;
  lat: number;
  lng: number;
  party_number: number;
  party_abbreviation: string;
  winner_name: string;
  votes: number;
};

export type TseWinnersMapResponse = {
  year: number;
  office_code: number;
  points: TseWinnerMapPoint[];
};

export type TseRankedCandidate = {
  candidate: TseCandidate;
  total_votes: number;
};

export type TseTopCandidatesResponse = {
  year: number;
  office_code: number | null;
  office_name: string | null;
  state: string | null;
  items: TseRankedCandidate[];
};

export type TsePartyPerformanceItem = {
  party: TseParty;
  total_votes: number;
  elected_count: number;
  candidates_count: number;
};

export type TsePartyPerformanceResponse = {
  year: number;
  office_code: number | null;
  office_name: string | null;
  state: string | null;
  items: TsePartyPerformanceItem[];
  total_votes: number;
  total_elected: number;
};

export type TseElectionStats = {
  election: TseElection;
  candidates_count: number;
  municipalities_count: number;
  total_votes: number;
};

export type TseSyncJob = {
  id: string;
  dataset: string;
  year: number;
  status: "pending" | "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  rows_processed: number;
  rows_total: number | null;
  candidates_imported: number;
  parties_imported: number;
  municipalities_imported: number;
  vote_results_imported: number;
  error_message: string | null;
  created_at: string;
};

/** Cargos TSE — codigos oficiais do CD_CARGO no dataset publico. */
export const TSE_OFFICES: Record<number, string> = {
  1: "Presidente",
  2: "Vice-presidente",
  3: "Governador",
  4: "Vice-governador",
  5: "Senador",
  6: "Deputado federal",
  7: "Deputado estadual",
  8: "Deputado distrital",
  9: "1º suplente",
  10: "2º suplente",
  11: "Prefeito",
  12: "Vice-prefeito",
  13: "Vereador",
};

export const TSE_STATES = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
  "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
  "RS", "RO", "RR", "SC", "SP", "SE", "TO",
] as const;
export type TseState = (typeof TSE_STATES)[number];


// --------------------------------------------------------- Neighborhoods

export type NeighborhoodStats = {
  neighborhood: string;
  total_places: number;
  total_votes: number;
  total_voters: number | null;
  avg_lat: number | null;
  avg_lng: number | null;
};

export type NeighborhoodStatsResponse = {
  items: NeighborhoodStats[];
  total_neighborhoods: number;
  total_votes: number;
};


/** Interaction = webhook event vinculado (ou nao) a um Contact. */
export type Interaction = {
  id: string;
  contact_id: string | null;
  phone: string | null;
  event_type: string | null;
  channel: string;
  external_event_id: string | null;
  payload_data: Record<string, unknown>;
  received_at: string; // ISO
  created_at: string;  // ISO
};
