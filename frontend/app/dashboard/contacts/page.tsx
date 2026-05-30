"use client";

/**
 * /dashboard/contacts — CRM list view com:
 *  - busca server-side (debounced 300ms) por nome
 *  - paginacao server-side
 *  - acoes Editar (mesmo dialog) e Excluir (AlertDialog de confirmacao)
 */
import { Plus, Search, Upload, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import { useDebouncedValue } from "@/lib/hooks";
import type { Contact, ContactTag, Page } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { ContactFormDialog } from "@/components/contacts/ContactFormDialog";
import { ImportContactsDialog } from "@/components/contacts/ImportContactsDialog";
import { makeContactColumns } from "@/components/contacts/columns";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;

export default function ContactsPage() {
  const [data, setData] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [pageIndex, setPageIndex] = useState(0);
  const [loading, setLoading] = useState(true);

  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, 300);

  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [availableTags, setAvailableTags] = useState<ContactTag[]>([]);

  const [editing, setEditing] = useState<Contact | null>(null);
  const [deleting, setDeleting] = useState<Contact | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  const load = useCallback(
    async (page: number, searchTerm: string, tag: string | null) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: String(page * PAGE_SIZE),
        });
        if (searchTerm.trim()) params.set("search", searchTerm.trim());
        if (tag) params.set("tag", tag);

        const res = await api<Page<Contact>>(`/v1/contacts?${params}`);
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

  // Reset para pagina 0 sempre que o termo de busca ou tag mudar
  useEffect(() => {
    load(0, search, tagFilter);
  }, [load, search, tagFilter]);

  // Carrega tags disponiveis (chips de filtro rapido)
  useEffect(() => {
    api<ContactTag[]>("/v1/contacts/tags")
      .then(setAvailableTags)
      .catch(() => setAvailableTags([]));
  }, []);

  const refresh = useCallback(
    () => load(pageIndex, search, tagFilter),
    [load, pageIndex, search, tagFilter],
  );

  async function handleConfirmDelete() {
    if (!deleting) return;
    setDeletingBusy(true);
    try {
      await api(`/v1/contacts/${deleting.id}`, { method: "DELETE" });
      toast.success("Contato excluído.");
      setDeleting(null);
      // Se removeu o ultimo da pagina, recua uma pagina
      const newTotal = total - 1;
      const lastPage = Math.max(0, Math.ceil(newTotal / PAGE_SIZE) - 1);
      load(Math.min(pageIndex, lastPage), search, tagFilter);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao excluir.");
    } finally {
      setDeletingBusy(false);
    }
  }

  const columns = useMemo(
    () =>
      makeContactColumns({
        onEdit: (c) => setEditing(c),
        onDelete: (c) => setDeleting(c),
      }),
    [],
  );

  return (
    <section className="max-w-7xl mx-auto px-6 py-8 space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Contatos</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            CRM da campanha — eleitores, lideranças, apoiadores e doadores.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ImportContactsDialog onImported={refresh}>
            <Button variant="outline">
              <Upload />
              Importar CSV
            </Button>
          </ImportContactsDialog>
          <ContactFormDialog mode="create" onSaved={refresh}>
            <Button>
              <Plus />
              Novo contato
            </Button>
          </ContactFormDialog>
        </div>
      </header>

      {/* Barra de busca + filtros tag */}
      <div className="space-y-3">
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Buscar por nome..."
            className="pl-9"
          />
        </div>

        {(availableTags.length > 0 || tagFilter) && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-1">
              Filtrar por tag:
            </span>
            {availableTags.slice(0, 12).map((t) => {
              const on = tagFilter === t.tag;
              return (
                <button
                  key={t.tag}
                  type="button"
                  onClick={() => setTagFilter(on ? null : t.tag)}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs transition-colors ${
                    on
                      ? "border-primary bg-primary/15 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground hover:border-primary/50"
                  }`}
                >
                  {t.tag}
                  <span className="text-[9px] opacity-70">({t.count})</span>
                  {on && <X className="w-3 h-3" />}
                </button>
              );
            })}
            {tagFilter && !availableTags.find((t) => t.tag === tagFilter) && (
              <button
                type="button"
                onClick={() => setTagFilter(null)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-primary bg-primary/15 text-xs"
              >
                {tagFilter}
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        )}
      </div>

      <DataTable
        columns={columns}
        data={data}
        total={total}
        pageSize={PAGE_SIZE}
        pageIndex={pageIndex}
        onPageChange={(p) => load(p, search, tagFilter)}
        isLoading={loading}
        emptyMessage={
          search || tagFilter
            ? `Nenhum contato encontrado com os filtros atuais.`
            : "Nenhum contato. Clique em 'Novo contato' para começar."
        }
      />

      {/* Dialog de edicao (controlled) */}
      <ContactFormDialog
        mode="edit"
        contact={editing}
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        onSaved={refresh}
      />

      {/* Confirmacao de exclusao */}
      <AlertDialog
        open={!!deleting}
        onOpenChange={(o) => !o && !deletingBusy && setDeleting(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir contato?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta ação não pode ser desfeita.{" "}
              <strong className="text-foreground">{deleting?.full_name}</strong>{" "}
              será removido permanentemente da campanha.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingBusy}>
              Cancelar
            </AlertDialogCancel>
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
