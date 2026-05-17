"use client";

/**
 * /dashboard/contacts — CRM list view.
 * - Paginacao server-side (limit/offset)
 * - Atualiza ao criar novo contato (via callback do Dialog)
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { Contact, Page } from "@/lib/types";
import { DataTable } from "@/components/ui/data-table";
import { contactColumns } from "@/components/contacts/columns";
import { CreateContactDialog } from "@/components/contacts/CreateContactDialog";

const PAGE_SIZE = 25;

export default function ContactsPage() {
  const [data, setData] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [pageIndex, setPageIndex] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    async (page: number) => {
      setLoading(true);
      try {
        const res = await api<Page<Contact>>(
          `/v1/contacts?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`,
        );
        setData(res.items);
        setTotal(res.total);
        setPageIndex(page);
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : "Erro ao carregar.";
        toast.error(msg);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    load(0);
  }, [load]);

  return (
    <section className="max-w-7xl mx-auto px-6 py-8 space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Contatos</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            CRM da campanha — eleitores, lideranças, apoiadores e doadores.
          </p>
        </div>
        <CreateContactDialog onCreated={() => load(pageIndex)} />
      </header>

      <DataTable
        columns={contactColumns}
        data={data}
        total={total}
        pageSize={PAGE_SIZE}
        pageIndex={pageIndex}
        onPageChange={load}
        isLoading={loading}
        emptyMessage="Nenhum contato. Clique em 'Novo contato' para começar."
      />
    </section>
  );
}
