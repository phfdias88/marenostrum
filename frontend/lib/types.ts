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
