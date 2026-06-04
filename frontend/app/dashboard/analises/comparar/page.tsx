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
  TseMunicipality,
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

          {/* Relatorio analitico (so quando tem 2+ candidatos) */}
          {pool.length >= 2 && <ComparisonReport pool={pool} />}
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
        <Link
          href={`/dashboard/analises/candidato/${c.id}`}
          className="font-bold truncate w-full hover:underline"
          title="Ver página completa"
        >
          {c.urn_name}
        </Link>
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
          <p className="font-medium truncate">
            {c.situation && !c.situation.startsWith("#") ? c.situation : "-"}
          </p>
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

      <Link
        href={`/dashboard/analises/candidato/${c.id}`}
        data-html2canvas-ignore
        className="mt-3 inline-flex w-full items-center justify-center gap-1.5 px-2 py-1.5 rounded-md bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors"
      >
        Ver página completa →
      </Link>
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
  // Filtro de cidade — busca + selecao
  const [muniSearch, setMuniSearch] = useState("");
  const muniDebounced = useDebounce(muniSearch, 300);
  const [muniResults, setMuniResults] = useState<TseMunicipality[]>([]);
  const [selectedMuni, setSelectedMuni] = useState<TseMunicipality | null>(null);

  // Busca municipios conforme digita (so se nao tem selecionado)
  useEffect(() => {
    if (selectedMuni) return;
    const q = muniDebounced.trim();
    if (q.length < 2) {
      setMuniResults([]);
      return;
    }
    const p = new URLSearchParams({ limit: "10", search: q });
    if (state) p.set("state", state);
    api<Page<TseMunicipality>>(`/v1/tse/municipalities?${p.toString()}`)
      .then((r) => setMuniResults(r.items))
      .catch(() => setMuniResults([]));
  }, [muniDebounced, state, selectedMuni]);

  useEffect(() => {
    const p = new URLSearchParams({ limit: "20" });
    if (state) p.set("state", state);
    if (office) p.set("office_code", office);
    if (debounced.trim()) p.set("search", debounced.trim());
    if (selectedMuni) p.set("municipality_id", selectedMuni.id);
    setLoading(true);
    api<Page<TseCandidate>>(`/v1/tse/candidates?${p.toString()}`)
      .then(setData)
      .catch(() => setData({ items: [], total: 0, limit: 20, offset: 0 }))
      .finally(() => setLoading(false));
  }, [state, office, debounced, selectedMuni]);

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
          {/* Filtro cidade: busca + chip de selecionada */}
          {selectedMuni ? (
            <div className="flex items-center gap-2 py-1 px-3 rounded-md bg-primary/10 border border-primary/40 text-sm">
              <span className="text-xs uppercase tracking-wider text-primary font-semibold">Cidade:</span>
              <span className="flex-1 font-semibold">
                {selectedMuni.name}<span className="text-muted-foreground font-normal">/{selectedMuni.state}</span>
              </span>
              <button
                onClick={() => { setSelectedMuni(null); setMuniSearch(""); }}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Remover filtro cidade"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={muniSearch}
                onChange={(e) => setMuniSearch(e.target.value)}
                placeholder="Filtrar por cidade (opcional)…"
                className="w-full pl-9 py-2 rounded-md bg-background border border-border text-sm"
              />
              {muniResults.length > 0 && (
                <div className="absolute z-10 top-full left-0 right-0 mt-1 rounded-md border bg-card shadow-xl max-h-48 overflow-auto divide-y divide-border">
                  {muniResults.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => { setSelectedMuni(m); setMuniResults([]); setMuniSearch(""); }}
                      className="w-full px-3 py-2 text-left hover:bg-accent/50 transition-colors text-sm flex items-center justify-between"
                    >
                      <span>{m.name}</span>
                      <span className="text-xs text-muted-foreground">{m.state}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
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
                <CandidatePhoto
                  candidateId={c.id}
                  name={c.urn_name}
                  partyNumber={c.party.number}
                  size="md"
                />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">
                    <span className="text-primary font-mono mr-1.5">{c.number}</span>
                    {c.urn_name}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {c.party.abbreviation} · {c.office_name} · {c.state} · {c.election.year}
                  </p>
                  {c.name && c.name.toLowerCase() !== c.urn_name.toLowerCase() && (
                    <p className="text-[10px] text-muted-foreground/70 truncate">
                      {c.name}
                    </p>
                  )}
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

// ------------------------------------------------------ comparison report

/**
 * Relatorio textual + comparativos abaixo dos cards.
 *
 * Calcula:
 * - Total geral (soma dos votos de todos)
 * - Diferenca entre lider e ultimo colocado (absoluta + %)
 * - Top 3 municipios por candidato (e quem foi mais forte em cada)
 * - Municipios "compartilhados" — onde os 2+ candidatos competem
 * - Patrimonio total declarado, receita total, despesa total
 * - Eficiencia eleitoral (votos por R$ gasto em campanha)
 */
function ComparisonReport({ pool }: { pool: TseCandidateResults[] }) {
  // Maior x menor
  const sorted = [...pool].sort((a, b) => b.total_votes - a.total_votes);
  const leader = sorted[0];
  const last = sorted[sorted.length - 1];
  const totalAll = pool.reduce((s, p) => s + p.total_votes, 0);
  const diffAbs = leader.total_votes - last.total_votes;
  const diffPct = last.total_votes > 0 ? (diffAbs / last.total_votes) * 100 : 100;

  // Municipios compartilhados — onde 2+ candidatos tem votos
  const muniMap = new Map<string, { name: string; state: string; votes: Map<string, number> }>();
  pool.forEach((p) => {
    p.results.forEach((r) => {
      const key = r.municipality.id;
      const slot =
        muniMap.get(key) ?? { name: r.municipality.name, state: r.municipality.state, votes: new Map() };
      slot.votes.set(p.candidate.id, r.votes);
      muniMap.set(key, slot);
    });
  });
  const sharedMunis = Array.from(muniMap.values()).filter((m) => m.votes.size >= 2);
  // Top 5 cidades compartilhadas onde a competicao foi mais acirrada
  const battlegrounds = sharedMunis
    .map((m) => {
      const votes = Array.from(m.votes.values());
      const top = Math.max(...votes);
      const totalCity = votes.reduce((s, v) => s + v, 0);
      return { ...m, top, totalCity };
    })
    .sort((a, b) => b.totalCity - a.totalCity)
    .slice(0, 5);

  // Eficiencia: votos/R$ despesa
  const efficiency = pool.map((p) => {
    const exp = p.candidate.expense_total ?? 0;
    return {
      name: p.candidate.urn_name,
      partyAbbr: p.candidate.party.abbreviation,
      eff: exp > 0 ? p.total_votes / exp : null,
      expense: exp,
      votes: p.total_votes,
    };
  });
  const bestEff = efficiency
    .filter((e) => e.eff !== null)
    .sort((a, b) => (b.eff ?? 0) - (a.eff ?? 0))[0];

  // Quem teve mais votos nos top X municipios — agrega por candidato
  const topCidadesPorCandidato = pool.map((p) => ({
    id: p.candidate.id,
    name: p.candidate.urn_name,
    partyAbbr: p.candidate.party.abbreviation,
    cidades: p.results.slice(0, 3).map((r) => ({
      name: r.municipality.name,
      uf: r.municipality.state,
      votes: r.votes,
    })),
  }));

  return (
    <section className="rounded-xl border bg-card p-5 sm:p-6 mb-6 space-y-5" data-html2canvas-ignore>
      <header className="flex items-center gap-2">
        <span className="grid place-items-center w-9 h-9 rounded-lg bg-primary/15 text-primary">
          <Trophy className="w-4 h-4" />
        </span>
        <div>
          <h2 className="font-bold text-lg">Relatório comparativo</h2>
          <p className="text-xs text-muted-foreground">
            Análise automática sobre {pool.length} candidatos · {sharedMunis.length} municípios em comum
          </p>
        </div>
      </header>

      {/* Insights principais — 4 mini-cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
        <div className="rounded-lg border bg-background/50 p-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Líder</p>
          <p className="font-bold mt-0.5 truncate">{leader.candidate.urn_name}</p>
          <p className="text-xs text-primary tabular-nums mt-1">
            {numberFmt.format(leader.total_votes)} votos
          </p>
        </div>
        <div className="rounded-lg border bg-background/50 p-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Diferença</p>
          <p className="font-bold mt-0.5 tabular-nums">{numberFmt.format(diffAbs)}</p>
          <p className="text-xs text-muted-foreground mt-1">
            {diffPct >= 1000 ? "+1000%" : diffPct.toFixed(1) + "%"} vs último
          </p>
        </div>
        <div className="rounded-lg border bg-background/50 p-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Total</p>
          <p className="font-bold mt-0.5 tabular-nums">{numberFmt.format(totalAll)}</p>
          <p className="text-xs text-muted-foreground mt-1">votos somados</p>
        </div>
        {bestEff && (
          <div className="rounded-lg border bg-background/50 p-3">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Mais eficiente</p>
            <p className="font-bold mt-0.5 truncate">{bestEff.name}</p>
            <p className="text-xs text-emerald-400 tabular-nums mt-1">
              {bestEff.eff?.toFixed(2)} votos / R$
            </p>
          </div>
        )}
      </div>

      {/* Top cidades por candidato */}
      <div>
        <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold mb-2">
          Berço eleitoral de cada candidato
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {topCidadesPorCandidato.map((c) => (
            <div key={c.id} className="rounded-lg border bg-background/40 p-3">
              <p className="font-semibold text-sm truncate">
                {c.name} <span className="text-xs text-muted-foreground">· {c.partyAbbr}</span>
              </p>
              <ol className="mt-1.5 space-y-1 text-xs">
                {c.cidades.map((m, i) => (
                  <li key={i} className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      <span className="text-primary font-bold mr-1">{i + 1}º</span>
                      {m.name}<span className="text-muted-foreground">/{m.uf}</span>
                    </span>
                    <span className="font-mono tabular-nums shrink-0">
                      {numberFmt.format(m.votes)}
                    </span>
                  </li>
                ))}
                {c.cidades.length === 0 && (
                  <li className="text-muted-foreground italic">Sem votos registrados.</li>
                )}
              </ol>
            </div>
          ))}
        </div>
      </div>

      {/* Cidades de batalha — onde 2+ disputaram */}
      {battlegrounds.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            Top 5 cidades disputadas (onde 2+ candidatos tiveram votos)
          </p>
          <div className="rounded-lg border bg-background/40 divide-y divide-border">
            {battlegrounds.map((m, i) => (
              <div key={i} className="px-3 py-2 flex items-center gap-3">
                <span className="text-xs text-muted-foreground tabular-nums w-6">{i + 1}º</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {m.name}<span className="text-muted-foreground">/{m.state}</span>
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {numberFmt.format(m.totalCity)} votos somados nos candidatos comparados
                  </p>
                </div>
                {/* Mini-segments por candidato */}
                <div className="flex gap-0.5 w-32 h-2 rounded-full overflow-hidden bg-muted shrink-0">
                  {Array.from(m.votes.entries()).map(([cid, v], j) => {
                    const p = pool.find((x) => x.candidate.id === cid);
                    const pct = (v / m.totalCity) * 100;
                    const colors = ["bg-primary", "bg-blue-500", "bg-emerald-500", "bg-rose-500"];
                    return (
                      <div
                        key={cid}
                        className={colors[j % colors.length]}
                        style={{ width: `${pct}%` }}
                        title={`${p?.candidate.urn_name}: ${numberFmt.format(v)} votos (${pct.toFixed(1)}%)`}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Resumo financeiro */}
      {pool.some((p) => p.candidate.expense_total) && (
        <div>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            Eficiência eleitoral (votos por R$ gasto em campanha)
          </p>
          <div className="rounded-lg border bg-background/40 divide-y divide-border">
            {efficiency
              .filter((e) => e.eff !== null)
              .sort((a, b) => (b.eff ?? 0) - (a.eff ?? 0))
              .map((e, i) => (
                <div key={i} className="px-3 py-2 flex items-center gap-3 text-sm">
                  <span className="text-xs text-muted-foreground tabular-nums w-6">{i + 1}º</span>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{e.name} <span className="text-xs text-muted-foreground">· {e.partyAbbr}</span></p>
                    <p className="text-[11px] text-muted-foreground">
                      {numberFmt.format(e.votes)} votos / {brl.format(e.expense)} gastos
                    </p>
                  </div>
                  <span className="font-mono font-bold text-emerald-400 tabular-nums">
                    {e.eff?.toFixed(2)} v/R$
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </section>
  );
}
