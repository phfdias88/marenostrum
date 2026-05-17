"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CONTACT_TYPE_LABELS, type Contact } from "@/lib/types";

type Handlers = {
  onEdit: (contact: Contact) => void;
  onDelete: (contact: Contact) => void;
};

/**
 * Factory de colunas — funcao em vez de constante para fechar sobre
 * onEdit/onDelete, que vem da pagina (precisam mexer no estado dela).
 */
export function makeContactColumns({
  onEdit,
  onDelete,
}: Handlers): ColumnDef<Contact>[] {
  return [
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
        <span className="text-muted-foreground">
          {row.original.email ?? "—"}
        </span>
      ),
    },
    {
      id: "location",
      header: "Bairro / Cidade",
      cell: ({ row }) => {
        const parts = [
          row.original.neighborhood,
          row.original.city,
        ].filter(Boolean);
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
    {
      id: "actions",
      header: () => <span className="sr-only">Ações</span>,
      cell: ({ row }) => {
        const contact = row.original;
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Abrir ações">
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuLabel>Ações</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => onEdit(contact)}>
                <Pencil />
                Editar
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => onDelete(contact)}
                className="text-destructive focus:text-destructive focus:bg-destructive/10"
              >
                <Trash2 />
                Excluir
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];
}
