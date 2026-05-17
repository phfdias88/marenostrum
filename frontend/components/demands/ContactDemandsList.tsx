"use client";

/**
 * Lista de demandas de UM contato — usada na tab "Demandas" do perfil.
 * Versao enxuta da DataTable (sem filtros globais; ja vem filtrada por contact_id).
 */
import { CalendarDays, ClipboardList, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { Demand, Page } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CreateDemandDialog } from "./CreateDemandDialog";
import { StatusDropdown } from "./StatusDropdown";

export function ContactDemandsList({
  contactId,
  contactName,
}: {
  contactId: string;
  contactName: string;
}) {
  const [demands, setDemands] = useState<Demand[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api<Page<Demand>>(
        `/v1/demands?contact_id=${contactId}&limit=100`,
      );
      setDemands(res.items);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao carregar.");
    } finally {
      setLoading(false);
    }
  }, [contactId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <CreateDemandDialog
          onSaved={load}
          contactId={contactId}
          contactName={contactName}
        >
          <Button size="sm">
            <Plus />
            Nova demanda
          </Button>
        </CreateDemandDialog>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : demands.length === 0 ? (
        <div className="text-center py-12 border border-dashed rounded-lg">
          <ClipboardList className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-2 text-sm text-muted-foreground">
            Nenhuma demanda aberta por este contato ainda.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {demands.map((d) => (
            <li
              key={d.id}
              className="rounded-lg border bg-card p-4 space-y-2"
            >
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <p className="font-medium">{d.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {d.category}
                    <span className="mx-1.5">·</span>
                    <CalendarDays className="inline h-3 w-3 mr-0.5" />
                    {new Date(d.created_at).toLocaleDateString("pt-BR")}
                  </p>
                </div>
                <StatusDropdown demand={d} onChanged={load} />
              </div>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap line-clamp-3">
                {d.description}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
