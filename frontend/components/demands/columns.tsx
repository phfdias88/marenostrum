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
import type { Demand } from "@/lib/types";
import { StatusDropdown } from "./StatusDropdown";

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
        <span className="text-xs text-muted-foreground">
          {new Date(row.original.created_at).toLocaleDateString("pt-BR")}
        </span>
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
