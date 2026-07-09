"use client";

/**
 * OrphanLeadsCard — "Novos leads do WhatsApp".
 *
 * Interações de webhook que chegaram SEM contato correspondente (lead quente
 * que mandou mensagem e não está no CRM). Card discreto (collapsible) acima
 * da tabela de contatos; só aparece se houver grupos órfãos.
 *
 * Ações:
 *  - "Criar contato": abre o dialog de novo contato com o telefone pré-preenchido
 *  - "Revincular existentes": POST /relink — vincula órfãs cujo telefone
 *    normalizado casa com um contato já cadastrado
 */
import { ChevronDown, Link2, MessageCircle, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { OrphanInteractionGroup } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ContactFormDialog } from "@/components/contacts/ContactFormDialog";

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h}h`;
  const d = Math.floor(h / 24);
  return `há ${d} dia${d > 1 ? "s" : ""}`;
}

export function OrphanLeadsCard({ onChanged }: { onChanged: () => void }) {
  const [groups, setGroups] = useState<OrphanInteractionGroup[] | null>(null);
  const [open, setOpen] = useState(false);
  const [relinking, setRelinking] = useState(false);

  const load = useCallback(() => {
    api<OrphanInteractionGroup[]>("/v1/contacts/orphan-interactions", {
      skipCache: true,
    })
      .then(setGroups)
      .catch(() => setGroups([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Sem leads órfãos (ou erro): não polui a página.
  if (!groups || groups.length === 0) return null;

  async function relink() {
    setRelinking(true);
    try {
      const r = await api<{ relinked: number }>(
        "/v1/contacts/orphan-interactions/relink",
        { method: "POST" },
      );
      if (r.relinked > 0) {
        toast.success(
          `${r.relinked} interação(ões) vinculada(s) a contatos existentes.`,
        );
        onChanged();
      } else {
        toast("Nenhuma interação órfã casa com contatos já cadastrados.");
      }
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao revincular.");
    } finally {
      setRelinking(false);
    }
  }

  return (
    <div className="rounded-xl border border-emerald-600/30 bg-emerald-500/[0.05]">
      {/* Header collapsible */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="inline-flex items-center gap-2 text-sm font-medium">
          <MessageCircle className="w-4 h-4 text-emerald-600" />
          Novos leads do WhatsApp ({groups.length})
          <span className="hidden sm:inline text-xs font-normal text-muted-foreground">
            mensagens recebidas de números fora do CRM
          </span>
        </span>
        <ChevronDown
          className={cn(
            "w-4 h-4 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          <ul className="divide-y divide-border/60 rounded-lg border bg-card">
            {groups.map((g) => (
              <li
                key={g.phone}
                className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium tabular-nums">{g.phone}</p>
                  <p className="text-xs text-muted-foreground">
                    {g.count} evento{g.count > 1 ? "s" : ""}
                    {g.last_event_type ? ` · ${g.last_event_type}` : ""} ·{" "}
                    {timeAgo(g.last_at)}
                  </p>
                </div>
                <ContactFormDialog
                  mode="create"
                  initialPhone={g.phone}
                  onSaved={() => {
                    // Contato criado com o telefone do lead: revincula as
                    // mensagens órfãs automaticamente (best-effort).
                    api("/v1/contacts/orphan-interactions/relink", {
                      method: "POST",
                    })
                      .catch(() => undefined)
                      .finally(() => {
                        load();
                        onChanged();
                      });
                  }}
                >
                  <Button variant="outline" size="sm">
                    <Plus />
                    Criar contato
                  </Button>
                </ContactFormDialog>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-xs text-muted-foreground">
              Já cadastrou o contato? Revincule as mensagens pelo telefone.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={relink}
              disabled={relinking}
            >
              <Link2 />
              {relinking ? "Revinculando..." : "Revincular existentes"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
