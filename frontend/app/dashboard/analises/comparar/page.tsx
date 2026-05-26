"use client";

/**
 * Analise comparativa (estilo Politique).
 * - Adiciona ate 4 candidatos (busca + clique pra adicionar)
 * - Mostra lado-a-lado: total votos, municipios, situacao, partido
 * - Barra de progresso normalizada pelo MAX dos selecionados
 */
import {
  ArrowLeft,
  Loader2,
  Plus,
  Search,
  Trophy,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type {
  Page,
  TseCandidate,
  TseCandidateResults,
} from "@/lib/types";
import { TSE_OFFICES, TSE_STATES } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { ExportShare } from "@/components/tse/ExportShare";

const MAX_COMPARE = 4;
const numberFmt = new Intl.NumberFormat("pt-BR");

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export default function CompararAnalysisPage() {
  const [pool, setPool] = useState<TseCandidateResults[]>([]);
  const [showSearch, setShowSearch] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const cardRef = useRef<HTMLDivElement>(null);

  // Hidrata a comparação a partir da URL (?ids=id1,id2,...) — link compartilhável
  useEffect(() => {
    const ids = new URLSearchParams(window.location.search)
      .get("ids")
      ?.split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, MAX_COMPARE);
    if (!ids || ids.length === 0) {
      setHydrating(false);
      return;
    }
    Promise.all(
      ids.map((id) =>
        api<TseCandidateResults>(`/v1/tse/candidates/${id}/results`).catch(() => null),
      ),
    )
      .then((rs) => setPool(rs.filter((r): r is TseCandidateResults => r !== null)))
      .finally(() => setHydrating(false));
  }, []);

  // Mantém a URL em sincronia com a seleção (sem recarregar a página)
  useEffect(() => {
    if (hydrating) return;
    const ids = pool.map((p) => p.candidate.id).join(",");
    const url = new URL(window.location.href);
    if (ids) url.searchParams.set("ids", ids);
    else url.searchParams.delete("ids");
    window.history.replaceState(null, "", url.toString());
  }, [pool, hydrating]);

  function add(res: TseCandidateResults) {
    if (pool.find((p) => p.candidate.id === res.candidate.id)) return;
    setPool((cur) => [...cur, res].slice(0, MAX_COMPARE));
  }

  function remove(id: string) {
    setPool((cur) => cur.filter((p) => p.candidate.id !== id));
  }

  const maxVotes = Math.max(1, ...pool.map((p) => p.total_votes));

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Análise comparativa</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Compare até {MAX_COMPARE} candidatos lado a lado.
          </p>
        </div>
        {pool.length >= 2 && (
          <div data-html2canvas-ignore>
            <ExportShare targetRef={cardRef} filename="comparativo-marenostrum" />
          </div>
        )}
      </header>

      {hydrating ? (
        <div className="py-16 text-center">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
        </div>
      ) : pool.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40 mb-6">
          <Trophy className="mx-auto h-10 w-10 text-muted-foreground" />
          <p className="text-lg font-semibold mt-3">Nenhum candidato adicionado</p>
          <p className="text-sm text-muted-foreground mt-1 mb-4">
            Adicione pelo menos 2 pra ver a comparação.
          </p>
          <button
            onClick={() => setShowSearch(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="w-4 h-4" /> Adicionar candidato
          </button>
        </div>
      ) : (
        <>
          <div
            ref={cardRef}
            className={`grid gap-4 mb-6`}
            style={{
              gridTemplateColumns: `repeat(${Math.min(pool.length + 1, MAX_COMPARE + 1)}, minmax(0, 1fr))`,
            }}
          >
            {pool.map((p) => (
              <CompareCard
                key={p.candidate.id}
                result={p}
                maxVotes={maxVotes}
                isLeader={pool.length > 1 && p.total_votes === maxVotes}
                onRemove={() => remove(p.candidate.id)}
              />
            ))}
            {pool.length < MAX_COMPARE && (
              <button
                data-html2canvas-ignore
                onClick={() => setShowSearch(true)}
                className="border border-dashed border-border rounded-xl flex flex-col items-center justify-center gap-2 hover:border-primary/60 hover:bg-card/40 transition min-h-[200px]"
              >
                <Plus className="w-8 h-8 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">
                  Adicionar candidato
                </span>
              </button>
            )}
          </div>
        </>
      )}

      {showSearch && (
        <SearchModal onPick={add} onClose={() => setShowSearch(false)} />
      )}
    </div>
  );
}

// ------------------------------------------------------ compare card

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

function CompareCard({
  result,
  maxVotes,
  isLeader,
  onRemove,
}: {
  result: TseCandidateResults;
  maxVotes: number;
  isLeader?: boolean;
  onRemove: () => void;
}) {
  const c = result.candidate;
  const pct = (result.total_votes / maxVotes) * 100;
  return (
    <div
      className={`rounded-xl border bg-card p-4 relative ${
        isLeader ? "border-primary ring-1 ring-primary/40" : "border-border"
      }`}
    >
      {isLeader && (
        <span className="absolute -top-2 left-1/2 -translate-x-1/2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold">
          <Trophy className="w-3 h-3" /> MAIS VOTADO
        </span>
      )}
      <button
        data-html2canvas-ignore
        onClick={onRemove}
        className="absolute top-2 right-2 text-muted-foreground hover:text-foreground p-1"
      >
        <X className="w-4 h-4" />
      </button>

      <div className="text-center pt-2 flex flex-col items-center">
        <CandidatePhoto
          candidateId={c.id}
          name={c.urn_name}
          partyNumber={c.party.number}
          size="lg"
        />
        <p className="text-xs font-mono text-primary mt-2">#{c.number}</p>
        <p className="font-bold truncate w-full">{c.urn_name}</p>
        <p className="text-xs text-muted-foreground truncate w-full">{c.name}</p>
        <div className="mt-1.5 flex justify-center">
          <ResultBadge status={c.result_status} size="sm" />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-1 text-center">
        <div className="text-xs">
          <p className="text-muted-foreground">Partido</p>
          <p className="font-medium">{c.party.abbreviation}</p>
        </div>
        <div className="text-xs">
          <p className="text-muted-foreground">Cargo</p>
          <p className="font-medium">{c.office_name}</p>
        </div>
        <div className="text-xs">
          <p className="text-muted-foreground">UF</p>
          <p className="font-medium">{c.state}</p>
        </div>
        <div className="text-xs">
          <p className="text-muted-foreground">Situação</p>
          <p className="font-medium truncate">{c.situation ?? "-"}</p>
        </div>
      </div>

      <hr className="my-3 border-border" />

      <div>
        <p className="text-xs uppercase tracking-wider text-muted-foreground">
          Total de votos
        </p>
        <p className="text-2xl font-bold text-primary mt-0.5">
          {numberFmt.format(result.total_votes)}
        </p>
        <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full bg-primary transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          {numberFmt.format(result.municipalities_with_votes)} município(s)
        </p>
      </div>

      {/* Dados ricos (patrimonio / financas) */}
      {(c.assets_total || c.revenue_total || c.expense_total) && (
        <>
          <hr className="my-3 border-border" />
          <dl className="space-y-1.5 text-xs">
            {c.assets_total ? (
              <CompareRow label="Patrimônio" value={brl.format(c.assets_total)} />
            ) : null}
            {c.revenue_total ? (
              <CompareRow
                label="Receita"
                value={brl.format(c.revenue_total)}
                tone="text-emerald-400"
              />
            ) : null}
            {c.expense_total ? (
              <CompareRow
                label="Despesa"
                value={brl.format(c.expense_total)}
                tone="text-amber-400"
              />
            ) : null}
          </dl>
        </>
      )}
    </div>
  );
}

function CompareRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`font-semibold ${tone ?? ""}`}>{value}</dd>
    </div>
  );
}

// ------------------------------------------------------ modal busca

function SearchModal({
  onPick,
  onClose,
}: {
  onPick: (r: TseCandidateResults) => void;
  onClose: () => void;
}) {
  const [state, setState] = useState("MG");
  const [office, setOffice] = useState("11");
  const [search, setSearch] = useState("");
  const debounced = useDebounce(search, 300);
  const [data, setData] = useState<Page<TseCandidate> | null>(null);
  const [loading, setLoading] = useState(false);
  const [picking, setPicking] = useState<string | null>(null);

  useEffect(() => {
    const p = new URLSearchParams({ limit: "20" });
    if (state) p.set("state", state);
    if (office) p.set("office_code", office);
    if (debounced.trim()) p.set("search", debounced.trim());
    setLoading(true);
    api<Page<TseCandidate>>(`/v1/tse/candidates?${p.toString()}`)
      .then(setData)
      .catch(() => setData({ items: [], total: 0, limit: 20, offset: 0 }))
      .finally(() => setLoading(false));
  }, [state, office, debounced]);

  async function pick(c: TseCandidate) {
    setPicking(c.id);
    try {
      const r = await api<TseCandidateResults>(
        `/v1/tse/candidates/${c.id}/results`,
      );
      onPick(r);
      onClose();
    } catch {
      setPicking(null);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 grid place-items-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <header className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="font-bold">Adicionar candidato</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="p-4 space-y-3 border-b border-border">
          <div className="grid grid-cols-12 gap-2">
            <select
              value={state}
              onChange={(e) => setState(e.target.value)}
              className="col-span-3 py-2 px-3 rounded-md bg-background border border-border text-sm"
            >
              <option value="">UF</option>
              {TSE_STATES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              value={office}
              onChange={(e) => setOffice(e.target.value)}
              className="col-span-4 py-2 px-3 rounded-md bg-background border border-border text-sm"
            >
              <option value="">Cargo</option>
              {Object.entries(TSE_OFFICES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <div className="col-span-5 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Nome…"
                className="w-full pl-9 py-2 rounded-md bg-background border border-border text-sm"
              />
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto divide-y divide-border">
          {loading ? (
            <div className="p-10 text-center">
              <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
            </div>
          ) : data?.items.length === 0 ? (
            <p className="p-10 text-center text-sm text-muted-foreground">
              Nenhum candidato.
            </p>
          ) : (
            data?.items.map((c) => (
              <button
                key={c.id}
                onClick={() => pick(c)}
                disabled={picking !== null}
                className="w-full p-3 hover:bg-accent/50 disabled:opacity-50 transition-colors text-left flex items-center gap-3"
              >
                <span className="grid place-items-center w-9 h-9 rounded-md bg-primary/15 text-primary font-bold text-xs shrink-0">
                  {c.number}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{c.urn_name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {c.party.abbreviation} · {c.office_name} · {c.state}
                  </p>
                </div>
                {picking === c.id ? (
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                ) : (
                  <Plus className="w-4 h-4 text-muted-foreground" />
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
