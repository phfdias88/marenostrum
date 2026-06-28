"use client";

/**
 * /dashboard/analises/adversarios — meu candidato + adversários monitorados.
 *
 * Persistência server-side via /v1/monitored. Permite:
 *  - Promover qualquer candidato a "meu candidato" (único por tenant)
 *  - Adicionar adversários a partir da busca TSE
 *  - Comparativo visual lado-a-lado (votos, eleito, cargo, UF)
 *  - Remover da lista
 */
import { ArrowLeft, BarChart3, Crown, Plus, Search, Star, Swords, Trash2, Trophy, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { MonitoredCandidateRead, TseCandidate } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ExportShare } from "@/components/tse/ExportShare";

const numberFmt = new Intl.NumberFormat("pt-BR");

export default function AdversariosPage() {
  const [items, setItems] = useState<MonitoredCandidateRead[] | null>(null);
  const [showSearch, setShowSearch] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const rows = await api<MonitoredCandidateRead[]>("/v1/monitored");
      setItems(rows);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao carregar.");
      setItems([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function add(candidateId: string, isMine: boolean) {
    try {
      await api<MonitoredCandidateRead>("/v1/monitored", {
        method: "POST",
        body: { candidate_id: candidateId, is_mine: isMine },
      });
      toast.success(isMine ? "Definido como meu candidato." : "Adversário adicionado.");
      setShowSearch(false);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro ao adicionar.");
    }
  }

  async function promote(monitoredId: string) {
    try {
      await api<MonitoredCandidateRead>(`/v1/monitored/${monitoredId}`, {
        method: "PATCH",
        body: { is_mine: true },
      });
      toast.success("Promovido a 'meu candidato'.");
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro.");
    }
  }

  async function remove(monitoredId: string) {
    try {
      await api(`/v1/monitored/${monitoredId}`, { method: "DELETE" });
      toast.success("Removido.");
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Erro.");
    }
  }

  const mine = items?.find((i) => i.is_mine) ?? null;
  const adversaries = items?.filter((i) => !i.is_mine) ?? [];

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/dashboard/analises"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Análises
        </Link>
        <button
          onClick={() => setShowSearch(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
        >
          <Plus className="w-4 h-4" /> Adicionar candidato
        </button>
      </div>

      <header className="mb-6">
        <h1 className="text-2xl font-bold inline-flex items-center gap-2">
          <Swords className="w-6 h-6 text-primary" /> Adversários monitorados
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Defina seu candidato + adversários e veja o comparativo persistente
          sempre que abrir o sistema.
        </p>
      </header>

      {items === null ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[0, 1].map((i) => (
            <div key={i} className="rounded-xl border bg-card p-5 h-44 animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState onAdd={() => setShowSearch(true)} />
      ) : (
        <div className="space-y-6">
          {/* Meu candidato */}
          <section>
            <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Meu candidato
            </h2>
            {mine ? (
              <Card
                m={mine}
                onPromote={() => {}}
                onRemove={() => remove(mine.id)}
                isMine
              />
            ) : (
              <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                Nenhum candidato definido. Adicione um e promova-o a "meu
                candidato" para destacá-lo.
              </div>
            )}
          </section>

          {/* Adversários */}
          {adversaries.length > 0 && (
            <section>
              <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
                Adversários ({adversaries.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {adversaries.map((m) => (
                  <Card
                    key={m.id}
                    m={m}
                    onPromote={() => promote(m.id)}
                    onRemove={() => remove(m.id)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Relatório comparativo — aparece com 2+ candidatos válidos */}
          <ComparisonReport items={items} reportRef={reportRef} />
        </div>
      )}

      {showSearch && (
        <SearchModal
          onClose={() => setShowSearch(false)}
          onPick={(id, isMine) => add(id, isMine)}
        />
      )}
    </div>
  );
}

// ==================================================== ComparisonReport

function ComparisonReport({
  items,
  reportRef,
}: {
  items: MonitoredCandidateRead[];
  reportRef: React.RefObject<HTMLDivElement>;
}) {
  // Só candidatos válidos (existem no TSE) e com votos pra comparar.
  const valid = items.filter((i) => i.candidate_found);
  if (valid.length < 2) return null;

  // Ordena por votos desc; "meu candidato" recebe destaque visual.
  const ranked = [...valid].sort(
    (a, b) => (b.candidate_total_votes ?? 0) - (a.candidate_total_votes ?? 0),
  );
  const maxVotes = Math.max(1, ...ranked.map((r) => r.candidate_total_votes ?? 0));
  const mineVotes = valid.find((i) => i.is_mine)?.candidate_total_votes ?? null;
  const leader = ranked[0];

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xs uppercase tracking-wider text-muted-foreground inline-flex items-center gap-1.5">
          <BarChart3 className="w-3.5 h-3.5" /> Relatório comparativo
        </h2>
        <div data-html2canvas-ignore>
          <ExportShare targetRef={reportRef} filename="comparativo-adversarios" />
        </div>
      </div>

      <div ref={reportRef} className="rounded-xl border bg-card p-4 sm:p-5 space-y-4">
        {/* Título dentro do card (aparece no PNG exportado) */}
        <div className="flex items-center gap-2 pb-1">
          <Swords className="w-4 h-4 text-primary" />
          <span className="font-semibold text-sm">
            Comparativo de candidatos monitorados
          </span>
        </div>

        {/* Barras de votos */}
        <div className="space-y-2.5">
          {ranked.map((r) => {
            const v = r.candidate_total_votes ?? 0;
            const pct = (v / maxVotes) * 100;
            return (
              <div key={r.id}>
                <div className="flex items-center justify-between gap-2 text-sm mb-0.5">
                  <span className="truncate flex items-center gap-1.5 min-w-0">
                    {r.is_mine && <Crown className="w-3.5 h-3.5 text-primary shrink-0" />}
                    <span className={`truncate ${r.is_mine ? "font-bold" : ""}`}>
                      {r.label ?? r.candidate_name}
                    </span>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {r.candidate_party_abbr}
                    </span>
                    {r.candidate_was_elected && (
                      <Trophy className="w-3 h-3 text-emerald-500 shrink-0" />
                    )}
                  </span>
                  <span className="font-mono font-semibold shrink-0 tabular-nums">
                    {numberFmt.format(v)}
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full ${r.is_mine ? "bg-primary" : "bg-primary/45"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Resumo: diferença do meu candidato pro líder */}
        {mineVotes != null && (
          <div className="rounded-lg bg-muted/40 p-3 text-sm">
            {leader.is_mine ? (
              <p className="text-emerald-600 font-medium">
                ✓ Seu candidato lidera o comparativo com{" "}
                {numberFmt.format(mineVotes)} votos.
              </p>
            ) : (
              <p className="text-muted-foreground">
                Seu candidato está{" "}
                <strong className="text-foreground">
                  {numberFmt.format((leader.candidate_total_votes ?? 0) - mineVotes)} votos
                </strong>{" "}
                atrás de{" "}
                <strong className="text-foreground">
                  {leader.label ?? leader.candidate_name}
                </strong>{" "}
                ({((mineVotes / (leader.candidate_total_votes ?? 1)) * 100).toFixed(1)}% dos votos do líder).
              </p>
            )}
          </div>
        )}

        {/* Tabela detalhada */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="py-1.5 pr-2 font-medium">Candidato</th>
                <th className="py-1.5 px-2 font-medium">Partido</th>
                <th className="py-1.5 px-2 font-medium">Cargo/UF</th>
                <th className="py-1.5 pl-2 font-medium text-right">Votos</th>
                <th className="py-1.5 pl-2 font-medium text-right">Situação</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((r) => (
                <tr key={r.id} className="border-b border-border/40 last:border-0">
                  <td className="py-2 pr-2">
                    <span className="flex items-center gap-1.5">
                      {r.is_mine && <Crown className="w-3 h-3 text-primary shrink-0" />}
                      <span className={r.is_mine ? "font-semibold" : ""}>
                        {r.label ?? r.candidate_name}
                      </span>
                    </span>
                  </td>
                  <td className="py-2 px-2 text-muted-foreground">{r.candidate_party_abbr ?? "—"}</td>
                  <td className="py-2 px-2 text-muted-foreground">
                    {r.candidate_office_name}{r.candidate_municipality_name ? ` · ${r.candidate_municipality_name}` : ""}{r.candidate_state ? ` · ${r.candidate_state}` : ""}
                  </td>
                  <td className="py-2 pl-2 text-right font-mono tabular-nums">
                    {r.candidate_total_votes != null ? numberFmt.format(r.candidate_total_votes) : "—"}
                  </td>
                  <td className="py-2 pl-2 text-right">
                    {r.candidate_was_elected == null ? (
                      <span className="text-muted-foreground text-xs">—</span>
                    ) : r.candidate_was_elected ? (
                      <span className="text-emerald-600 text-xs font-semibold">Eleito</span>
                    ) : (
                      <span className="text-muted-foreground text-xs">Não eleito</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="text-[10px] text-muted-foreground text-right">
          MareNostrum · Inteligência de Dados &amp; Consultoria
        </p>
      </div>
    </section>
  );
}

// ============================================================ Card

function Card({
  m,
  onPromote,
  onRemove,
  isMine,
}: {
  m: MonitoredCandidateRead;
  onPromote: () => void;
  onRemove: () => void;
  isMine?: boolean;
}) {
  if (!m.candidate_found) {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
        <p className="text-sm font-medium text-amber-700">
          Candidato removido do TSE
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          {m.label ?? "—"} (ID {m.candidate_id.slice(0, 8)}…)
        </p>
        <button
          onClick={onRemove}
          className="mt-2 text-xs text-destructive hover:underline"
        >
          Remover da lista
        </button>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border bg-card p-4 relative ${
        isMine ? "border-primary ring-1 ring-primary/40" : "border-border"
      }`}
    >
      {isMine && (
        <span className="absolute -top-2 left-1/2 -translate-x-1/2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold">
          <Crown className="w-3 h-3" /> MEU CANDIDATO
        </span>
      )}
      <div className="flex items-start gap-3">
        <CandidatePhoto
          candidateId={m.candidate_id}
          name={m.candidate_name ?? m.label ?? "?"}
          partyNumber={m.candidate_number ?? 0}
          size="lg"
        />
        <div className="flex-1 min-w-0">
          <Link
            href={`/dashboard/analises/candidato/${m.candidate_id}`}
            className="font-semibold hover:underline truncate block"
          >
            {m.label ?? m.candidate_name}
          </Link>
          <p className="text-xs text-muted-foreground truncate">
            {m.candidate_number} · {m.candidate_party_abbr} · {m.candidate_office_name}
            {m.candidate_municipality_name ? ` · ${m.candidate_municipality_name}` : ""}
            {m.candidate_state ? ` · ${m.candidate_state}` : ""}
          </p>
          <div className="flex items-center gap-3 mt-2 text-sm">
            <span className="font-mono font-semibold">
              {m.candidate_total_votes != null
                ? numberFmt.format(m.candidate_total_votes)
                : "—"}{" "}
              <span className="text-xs text-muted-foreground">votos</span>
            </span>
            {m.candidate_was_elected != null && (
              <span
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                  m.candidate_was_elected
                    ? "bg-emerald-500/20 text-emerald-600"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {m.candidate_was_elected && <Trophy className="w-3 h-3" />}
                {m.candidate_was_elected ? "ELEITO" : "NÃO ELEITO"}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-end gap-2 mt-3 pt-3 border-t border-border/40">
        {!isMine && (
          <button
            onClick={onPromote}
            className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-primary/40 text-primary hover:bg-primary/10"
            title="Definir como meu candidato"
          >
            <Star className="w-3 h-3" /> Promover
          </button>
        )}
        <button
          onClick={onRemove}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-border text-muted-foreground hover:text-destructive hover:border-destructive/40"
        >
          <Trash2 className="w-3 h-3" /> Remover
        </button>
      </div>
    </div>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
      <Swords className="mx-auto h-9 w-9 text-muted-foreground" />
      <p className="mt-3 font-semibold">Ainda sem candidatos monitorados</p>
      <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
        Adicione seu candidato e até 3-5 adversários pra ter um painel
        comparativo persistente.
      </p>
      <button
        onClick={onAdd}
        className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
      >
        <Plus className="w-4 h-4" /> Adicionar candidato
      </button>
    </div>
  );
}

// ============================================================ SearchModal

function SearchModal({
  onClose,
  onPick,
}: {
  onClose: () => void;
  onPick: (candidateId: string, isMine: boolean) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<TseCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [mineMode, setMineMode] = useState(false);

  useEffect(() => {
    if (q.trim().length < 3) {
      setResults([]);
      return;
    }
    setSearching(true);
    const t = setTimeout(() => {
      api<{ items: TseCandidate[] }>(
        `/v1/tse/candidates?search=${encodeURIComponent(q.trim())}&limit=20`,
      )
        .then((r) => setResults(r.items))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div
      className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-start justify-center pt-16 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold">Adicionar candidato</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={mineMode}
              onChange={(e) => setMineMode(e.target.checked)}
            />
            Definir como <strong className="text-primary">meu candidato</strong>
          </label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar por nome (mín 3 letras)..."
              className="w-full pl-9 pr-3 py-2 rounded-md bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
              autoFocus
            />
          </div>
          <div className="max-h-[50vh] overflow-y-auto space-y-1">
            {searching && (
              <p className="text-xs text-muted-foreground text-center py-4">
                Buscando…
              </p>
            )}
            {!searching && q.length >= 3 && results.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-4">
                Nenhum candidato encontrado.
              </p>
            )}
            {results.map((c) => (
              <button
                key={c.id}
                onClick={() => onPick(c.id, mineMode)}
                className="w-full text-left flex items-start gap-3 p-2 rounded-md hover:bg-accent transition-colors"
              >
                <CandidatePhoto
                  candidateId={c.id}
                  name={c.urn_name}
                  partyNumber={c.party.number}
                  size="md"
                />
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{c.urn_name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {c.number} · {c.party.abbreviation} · {c.office_name} ·{" "}
                    {c.state} · {c.election.year}
                  </p>
                  {c.name && c.name.toLowerCase() !== c.urn_name.toLowerCase() && (
                    <p className="text-[10px] text-muted-foreground/70 truncate">
                      {c.name}
                    </p>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
