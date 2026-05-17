"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { CONTACT_TYPE_LABELS, type Contact } from "@/lib/types";

/**
 * Colunas da DataTable de contatos.
 * Mantida em arquivo separado pra ficar facil estender depois (sort, filtro).
 */
export const contactColumns: ColumnDef<Contact>[] = [
  {
    accessorKey: "full_name",
    header: "Nome",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.full_name}</span>
    ),
  },
  {
    accessorKey: "phone",
    header: "Telefone",
    cell: ({ row }) => row.original.phone ?? "—",
  },
  {
    accessorKey: "email",
    header: "Email",
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.original.email ?? "—"}</span>
    ),
  },
  {
    id: "location",
    header: "Bairro / Cidade",
    cell: ({ row }) => {
      const parts = [row.original.neighborhood, row.original.city].filter(Boolean);
      return parts.length ? parts.join(" — ") : "—";
    },
  },
  {
    accessorKey: "type",
    header: "Tipo",
    cell: ({ row }) => (
      <span className="inline-flex items-center rounded-full bg-accent px-2.5 py-0.5 text-xs font-medium text-accent-foreground">
        {CONTACT_TYPE_LABELS[row.original.type]}
      </span>
    ),
  },
  {
    id: "geo",
    header: "Geo",
    cell: ({ row }) =>
      row.original.latitude != null && row.original.longitude != null ? (
        <span className="text-xs text-emerald-600">📍 sim</span>
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      ),
  },
];
