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
