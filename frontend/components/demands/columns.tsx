"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { MoreHorizontal, Trash2 } from "lucide-react";
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
import { cn } from "@/lib/utils";
import type { Demand } from "@/lib/types";
import { StatusDropdown } from "./StatusDropdown";

/**
 * Badge de idade — só em demandas VIVAS (aberta/em andamento).
 * "há N dias": neutro até 7d, amber >7d, vermelho >15d (parada demais).
 */
function AgeBadge({ demand }: { demand: Demand }) {
  if (demand.status !== "aberta" && demand.status !== "em_andamento") {
    return null;
  }
  const days = Math.floor(
    (Date.now() - new Date(demand.created_at).getTime()) / 86_400_000,
  );
  const label = days <= 0 ? "hoje" : `há ${days} dia${days > 1 ? "s" : ""}`;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-transparent px-2 py-0.5 text-[10px] font-medium",
        days > 15
          ? "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-400"
          : days > 7
            ? "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-400"
            : "bg-muted text-muted-foreground",
      )}
      title={`Criada ${label} — sem resolução`}
    >
      {label}
    </span>
  );
}

type Handlers = {
  onDelete: (demand: Demand) => void;
  onStatusChanged: () => void;
};

export function makeDemandColumns({
  onDelete,
  onStatusChanged,
}: Handlers): ColumnDef<Demand>[] {
  return [
    {
      accessorKey: "title",
      header: "Demanda",
      cell: ({ row }) => (
        <div>
          <p className="font-medium">{row.original.title}</p>
          <p className="text-xs text-muted-foreground line-clamp-1">
            {row.original.description}
          </p>
        </div>
      ),
    },
    {
      id: "contact",
      header: "Contato",
      cell: ({ row }) => (
        <Link
          href={`/dashboard/contacts/${row.original.contact.id}`}
          className="text-sm hover:text-primary hover:underline underline-offset-2"
        >
          {row.original.contact.full_name}
        </Link>
      ),
    },
    {
      accessorKey: "category",
      header: "Categoria",
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {row.original.category}
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <StatusDropdown demand={row.original} onChanged={onStatusChanged} />
      ),
    },
    {
      accessorKey: "created_at",
      header: "Criada em",
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {new Date(row.original.created_at).toLocaleDateString("pt-BR")}
          </span>
          <AgeBadge demand={row.original} />
        </div>
      ),
    },
    {
      id: "actions",
      header: () => <span className="sr-only">Ações</span>,
      cell: ({ row }) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuLabel>Ações</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => onDelete(row.original)}
              className="text-destructive focus:text-destructive focus:bg-destructive/10"
            >
              <Trash2 />
              Excluir
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];
}
