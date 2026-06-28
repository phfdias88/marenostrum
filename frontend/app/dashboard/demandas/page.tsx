"use client";

/**
 * /dashboard/demandas — visao GLOBAL de demandas do mandato.
 * Filtra por status (chips clicaveis no topo) + paginacao server-side.
 */
import { Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import {
  DEMAND_STATUS_LABELS,
  type Demand,
  type DemandStatus,
  type Page,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CreateDemandDialog } from "@/components/demands/CreateDemandDialog";
import { makeDemandColumns } from "@/components/demands/columns";

const PAGE_SIZE = 25;

type StatusFilter = DemandStatus | "todos";

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "todos", label: "Todas" },
  { value: "aberta", label: DEMAND_STATUS_LABELS.aberta },
  { value: "em_andamento", label: DEMAND_STATUS_LABELS.em_andamento },
  { value: "resolvida", label: DEMAND_STATUS_LABELS.resolvida },
  { value: "cancelada", label: DEMAND_STATUS_LABELS.cancelada },
];

export default function DemandasPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("todos");
  const [data, setData] = useState<Demand[]>([]);
  const [total, setTotal] = useState(0);
  const [pageIndex, setPageIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<Demand | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  const load = useCallback(
    async (page: number, filter: StatusFilter) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: String(page * PAGE_SIZE),
        });
        if (filter !== "todos") params.set("status", filter);

        const res = await api<Page<Demand>>(`/v1/demands?${params}`);
        setData(res.items);
        setTotal(res.total);
        setPageIndex(page);
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Erro ao carregar.");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    load(0, statusFilter);
  }, [load, statusFilter]);

  const refresh = useCallback(
    () => load(pageIndex, statusFilter),
    [load, pageIndex, statusFilter],
  );

  async function handleConfirmDelete() {
    if (!deleting) return;
    setDeletingBusy(true);
    try {
      await api(`/v1/demands/${deleting.id}`, { method: "DELETE" });
      toast.success("Demanda excluída.");
      setDeleting(null);
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao excluir.");
    } finally {
      setDeletingBusy(false);
    }
  }

  const columns = useMemo(
    () =>
      makeDemandColumns({
        onDelete: (d) => setDeleting(d),
        onStatusChanged: refresh,
      }),
    [refresh],
  );

  return (
    <section className="max-w-7xl mx-auto px-6 py-8 space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Demandas</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Pedidos da população — acompanhamento do gabinete.
          </p>
        </div>
        <CreateDemandDialog onSaved={refresh}>
          <Button>
            <Plus />
            Nova demanda
          </Button>
        </CreateDemandDialog>
      </header>

      {/* Chips de filtro por status */}
      <div className="flex gap-2 flex-wrap">
        {STATUS_FILTERS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setStatusFilter(value)}
            className={cn(
              "px-3 py-1.5 text-sm rounded-full border transition-colors",
              statusFilter === value
                ? "bg-foreground text-background border-foreground"
                : "bg-card text-muted-foreground border-border hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <DataTable
        columns={columns}
        data={data}
        total={total}
        pageSize={PAGE_SIZE}
        pageIndex={pageIndex}
        onPageChange={(p) => load(p, statusFilter)}
        isLoading={loading}
        emptyMessage={
          statusFilter === "todos"
            ? "Nenhuma demanda. Clique em 'Nova demanda' pra começar."
            : `Nenhuma demanda com status "${DEMAND_STATUS_LABELS[statusFilter as DemandStatus]}".`
        }
      />

      <AlertDialog
        open={!!deleting}
        onOpenChange={(o) => !o && !deletingBusy && setDeleting(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir demanda?</AlertDialogTitle>
            <AlertDialogDescription>
              <strong className="text-foreground">{deleting?.title}</strong> será
              removida permanentemente — esta ação não pode ser desfeita. Se quiser
              manter o histórico, em vez de excluir mude o status para{" "}
              <em>Cancelada</em>.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingBusy}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              disabled={deletingBusy}
              className={cn(buttonVariants({ variant: "destructive" }))}
            >
              {deletingBusy ? "Excluindo..." : "Excluir"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
