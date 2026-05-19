/** Tipos espelhando os schemas Pydantic do backend. */

export type ContactType = "voter" | "leader" | "supporter" | "donor" | "other";

export type Contact = {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  neighborhood: string | null;
  city: string | null;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  birth_date: string | null; // ISO date "YYYY-MM-DD"
  type: ContactType;
  notes: string | null;
  created_at: string;
  updated_at: string;
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
  party: TseParty;
  election: TseElection;
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

export type TseTopCandidateInMunicipality = {
  candidate: TseCandidate;
  votes: number;
};

export type TseMunicipalityResults = {
  municipality: TseMunicipality;
  results: TseTopCandidateInMunicipality[];
  total_results: number;
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
