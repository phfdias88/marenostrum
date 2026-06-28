"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { ExternalLink, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";

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
 * Colunas da DataTable de contatos.
 * Factory function porque a coluna "actions" precisa fechar sobre
 * setEditing/setDeleting do componente pai.
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
        // Nome clicavel = atalho rapido pro perfil
        <Link
          href={`/dashboard/contacts/${row.original.id}`}
          className="font-medium hover:text-primary hover:underline underline-offset-2"
        >
          {row.original.full_name}
        </Link>
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
        return parts.length ? parts.join(" · ") : "—";
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
      id: "tags",
      header: "Tags",
      cell: ({ row }) => {
        const tags = row.original.tags ?? [];
        if (!tags.length) return <span className="text-xs text-muted-foreground">—</span>;
        // Mostra ate' 2 + "+N" se sobrar
        const shown = tags.slice(0, 2);
        const extra = tags.length - shown.length;
        return (
          <div className="flex flex-wrap gap-1">
            {shown.map((t) => (
              <span
                key={t}
                className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-medium"
              >
                {t}
              </span>
            ))}
            {extra > 0 && (
              <span className="text-[10px] text-muted-foreground self-center">
                +{extra}
              </span>
            )}
          </div>
        );
      },
    },
    {
      id: "created_by",
      header: "Cadastrado por",
      cell: ({ row }) =>
        row.original.created_by_name ? (
          <span className="text-xs text-foreground">{row.original.created_by_name}</span>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
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
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuLabel>Ações</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href={`/dashboard/contacts/${contact.id}`}>
                  <ExternalLink />
                  Ver perfil
                </Link>
              </DropdownMenuItem>
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
