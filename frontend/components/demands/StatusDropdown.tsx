"use client";

/**
 * Dropdown rapido pra mudar status de uma demanda direto da DataTable.
 * Optimistic update: muda visualmente IMEDIATO; reverte se a API falhar.
 */
import { Check, ChevronDown } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import {
  DEMAND_STATUS_BADGE,
  DEMAND_STATUS_LABELS,
  type Demand,
  type DemandStatus,
} from "@/lib/types";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";

const ORDER: DemandStatus[] = ["aberta", "em_andamento", "resolvida", "cancelada"];

export function StatusDropdown({
  demand,
  onChanged,
}: {
  demand: Demand;
  onChanged: () => void;
}) {
  const [optimistic, setOptimistic] = useState<DemandStatus>(demand.status);

  async function change(next: DemandStatus) {
    if (next === optimistic) return;
    const previous = optimistic;
    setOptimistic(next); // optimistic

    try {
      await api(`/v1/demands/${demand.id}/status`, {
        method: "PATCH",
        body: { status: next },
      });
      onChanged();
    } catch (err) {
      setOptimistic(previous); // rollback visual
      toast.error(err instanceof ApiError ? err.message : "Falha ao mudar status.");
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="inline-flex items-center gap-1 cursor-pointer"
        aria-label="Mudar status"
      >
        <Badge variant={DEMAND_STATUS_BADGE[optimistic]}>
          {DEMAND_STATUS_LABELS[optimistic]}
        </Badge>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-44">
        {ORDER.map((s) => (
          <DropdownMenuItem
            key={s}
            onClick={() => change(s)}
            className="justify-between"
          >
            <span className="inline-flex items-center gap-2">
              <Badge variant={DEMAND_STATUS_BADGE[s]} className="px-1.5 py-0">
                {DEMAND_STATUS_LABELS[s]}
              </Badge>
            </span>
            {s === optimistic && <Check className="h-3.5 w-3.5" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
