"use client";

/**
 * Comparar municípios lado a lado — /dashboard/analises/comparar-municipios.
 * - adiciona até 4 cidades (busca modal — são 5.571)
 * - mostra vencedor de prefeito (2024), % e votos, + total nominal
 * - URL compartilhável ?ids=muniId1,muniId2
 * - Exportar PNG
 */
import { ArrowLeft, Loader2, MapPin, Plus, Search, Trophy, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { Page, TseMunicipality, TseMunicipalityResults } from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { StateFlag } from "@/components/tse/StateFlag";
import { ExportShare } from "@/components/tse/ExportShare";

const MAX = 4;
const numberFmt = new Intl.NumberFormat("pt-BR");
const pctFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

async function fetchMuni(id: string): Promise<TseMunicipalityResults | null> {
  return api<TseMunicipalityResults>(
    `/v1/tse/municipalities/${id}/top-candidates?office_code=11&year=2024&limit=5`,
  ).catch(() => null);
}

export default function CompararMunicipiosPage() {
  const [pool, setPool] = useState<TseMunicipalityResults[]>([]);
  const [showSearch, setShowSearch] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const cardRef = useRef<HTMLDivElement>(null);

  // Hidrata da URL ?ids=
  useEffect(() => {
    const ids = new URLSearchParams(window.location.search)
      .get("ids")
      ?.split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, MAX);
    if (!ids || ids.length === 0) {
      setHydrating(false);
      return;
    }
    Promise.all(ids.map(fetchMuni))
      .then((rs) => setPool(rs.filter((r): r is TseMunicipalityResults => r !== null)))
      .finally(() => setHydrating(false));
  }, []);

  // Sincroniza URL
  useEffect(() => {
    if (hydrating) return;
    const ids = pool.map((p) => p.municipality.id).join(",");
    const url = new URL(window.location.href);
    if (ids) url.searchParams.set("ids", ids);
    else url.searchParams.delete("ids");
    window.history.replaceState(null, "", url.toString());
  }, [pool, hydrating]);

  function add(res: TseMunicipalityResults) {
    if (pool.find((p) => p.municipality.id === res.municipality.id)) return;
    setPool((cur) => [...cur, res].slice(0, MAX));
  }
  function remove(id: string) {
    setPool((cur) => cur.filter((p) => p.municipality.id !== id));
  }

  const maxVotes = Math.max(1, ...pool.map((p) => p.total_votes));

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/dashboard/analises"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Análises
        </Link>
        {pool.length >= 2 && (
          <div data-html2canvas-ignore>
            <ExportShare targetRef={cardRef} filename="comparar-municipios" />
          </div>
        )}
      </div>

      <header className="mb-6">
        <h1 className="text-2xl font-bold">Comparar municípios</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Eleição municipal de 2024 (Prefeito/Vereador) — até {MAX} cidades lado a
          lado: prefeito eleito, votos e participação.
        </p>
      </header>

      {hydrating ? (
        <div className="py-16 text-center">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
        </div>
      ) : pool.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
          <MapPin className="mx-auto h-10 w-10 text-muted-foreground" />
          <p className="text-lg font-semibold mt-3">Nenhuma cidade adicionada</p>
          <p className="text-sm text-muted-foreground mt-1 mb-4">
            Adicione pelo menos 2 pra comparar.
          </p>
          <button
            onClick={() => setShowSearch(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="w-4 h-4" /> Adicionar cidade
          </button>
        </div>
      ) : (
        <div
          ref={cardRef}
          className="grid gap-4"
          style={{
            gridTemplateColumns: `repeat(${Math.min(pool.length + 1, MAX + 1)}, minmax(0, 1fr))`,
          }}
        >
          {pool.map((p) => (
            <MuniCard key={p.municipality.id} res={p} maxVotes={maxVotes} onRemove={() => remove(p.municipality.id)} />
          ))}
          {pool.length < MAX && (
            <button
              data-html2canvas-ignore
              onClick={() => setShowSearch(true)}
              className="border border-dashed border-border rounded-xl flex flex-col items-center justify-center gap-2 hover:border-primary/60 hover:bg-card/40 transition min-h-[220px]"
            >
              <Plus className="w-8 h-8 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Adicionar cidade</span>
            </button>
          )}
        </div>
      )}

      {showSearch && <SearchModal onPick={add} onClose={() => setShowSearch(false)} />}
    </div>
  );
}

function MuniCard({
  res,
  maxVotes,
  onRemove,
}: {
  res: TseMunicipalityResults;
  maxVotes: number;
  onRemove: () => void;
}) {
  const m = res.municipality;
  const winner = res.results[0];
  const pct = res.total_votes > 0 && winner ? (winner.votes / res.total_votes) * 100 : 0;
  return (
    <div className="rounded-xl border border-border bg-card p-4 relative">
      <button
        data-html2canvas-ignore
        onClick={onRemove}
        className="absolute top-2 right-2 text-muted-foreground hover:text-foreground p-1"
      >
        <X className="w-4 h-4" />
      </button>
      <div className="flex flex-col items-center text-center pt-1">
        <StateFlag uf={m.state} size="lg" className="!w-16 !h-11 shadow" />
        <Link
          href={`/dashboard/analises/municipio/${m.id}`}
          className="font-bold mt-2 hover:underline"
        >
          {m.name}
        </Link>
        <p className="text-xs text-muted-foreground">{m.state} · TSE {m.tse_code}</p>
      </div>

      <hr className="my-3 border-border" />

      {winner ? (
        <>
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1">
            <Trophy className="w-3 h-3 text-primary" /> Prefeito eleito
          </p>
          <Link
            href={`/dashboard/analises/candidato/${winner.candidate.id}`}
            className="flex items-center gap-2 hover:bg-accent/40 rounded-md p-1 -m-1 transition-colors"
          >
            <CandidatePhoto
              candidateId={winner.candidate.id}
              name={winner.candidate.urn_name}
              partyNumber={winner.candidate.party.number}
              size="md"
            />
            <div className="min-w-0">
              <p className="font-semibold truncate flex items-center gap-1.5">
                {winner.candidate.urn_name}
                <ResultBadge status={winner.candidate.result_status} size="sm" />
              </p>
              <p
                className="text-xs text-muted-foreground"
                title="% dos votos nominais da cidade"
              >
                {winner.candidate.party.abbreviation} · {pctFmt.format(pct)}%
              </p>
            </div>
          </Link>
          <p className="text-2xl font-bold text-primary mt-3">
            {numberFmt.format(winner.votes)}
          </p>
          <p className="text-xs text-muted-foreground">votos do vencedor</p>
          <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary"
              style={{ width: `${(res.total_votes / maxVotes) * 100}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            {numberFmt.format(res.total_votes)} votos válidos na cidade
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground text-center py-4">
          Sem dados de prefeito.
        </p>
      )}
    </div>
  );
}

function SearchModal({
  onPick,
  onClose,
}: {
  onPick: (r: TseMunicipalityResults) => void;
  onClose: () => void;
}) {
  const [state, setState] = useState("");
  const [search, setSearch] = useState("");
  const debounced = useDebounce(search, 300);
  const [data, setData] = useState<Page<TseMunicipality> | null>(null);
  const [loading, setLoading] = useState(false);
  const [picking, setPicking] = useState<string | null>(null);

  useEffect(() => {
    const p = new URLSearchParams({ limit: "25" });
    if (state) p.set("state", state);
    if (debounced.trim()) p.set("search", debounced.trim());
    setLoading(true);
    api<Page<TseMunicipality>>(`/v1/tse/municipalities?${p.toString()}`)
      .then(setData)
      .catch(() => setData({ items: [], total: 0, limit: 25, offset: 0 }))
      .finally(() => setLoading(false));
  }, [state, debounced]);

  async function pick(m: TseMunicipality) {
    setPicking(m.id);
    const r = await fetchMuni(m.id);
    if (r) {
      onPick(r);
      onClose();
    } else {
      setPicking(null);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 grid place-items-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <header className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="font-bold">Adicionar cidade</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </header>
        <div className="p-4 border-b border-border grid grid-cols-12 gap-2">
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
          <div className="col-span-9 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Nome do município…"
              className="w-full pl-9 py-2 rounded-md bg-background border border-border text-sm"
            />
          </div>
        </div>
        <div className="flex-1 overflow-auto divide-y divide-border">
          {loading ? (
            <div className="p-10 text-center">
              <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
            </div>
          ) : data?.items.length === 0 ? (
            <p className="p-10 text-center text-sm text-muted-foreground">Nenhum município.</p>
          ) : (
            data?.items.map((m) => (
              <button
                key={m.id}
                onClick={() => pick(m)}
                disabled={picking !== null}
                className="w-full p-3 hover:bg-accent/50 disabled:opacity-50 transition-colors text-left flex items-center gap-3"
              >
                <StateFlag uf={m.state} size="sm" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{m.name}</p>
                  <p className="text-xs text-muted-foreground">{m.state}</p>
                </div>
                {picking === m.id ? (
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
