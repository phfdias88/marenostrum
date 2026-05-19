"use client";

/**
 * Análise por Bairro (TSE) — candidato-cêntrica.
 *
 * Fluxo:
 *  1. UF + Cargo + busca de Município
 *  2. Busca/seleciona o candidato (daquele município+cargo)
 *  3. Mostra votos DELE por bairro: ranking (esquerda) + mapa de bolhas (direita)
 *
 * Usa /tse/candidates/{id}/by-neighborhood?municipality_id=X.
 * Requer votacao_secao_<UF> sincronizado (so MG por enquanto; demais em import).
 */
import { ArrowLeft, Loader2, MapPin, Search, Vote, X } from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  Page,
  TseCandidate,
  TseCandidateByNeighborhoodResponse,
  TseMunicipality,
} from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";

const CandidateNeighborhoodMap = dynamic(
  () => import("@/components/map/CandidateNeighborhoodMap"),
  { ssr: false, loading: () => <MapBox>Carregando mapa…</MapBox> },
);

const numberFmt = new Intl.NumberFormat("pt-BR");
const OFFICES = [
  { value: "11", label: "Prefeito" },
  { value: "13", label: "Vereador" },
];

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export default function BairrosPage() {
  const [state, setState] = useState("MG");
  const [office, setOffice] = useState("11");
  const [muni, setMuni] = useState<TseMunicipality | null>(null);
  const [candidate, setCandidate] = useState<TseCandidate | null>(null);

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-6 flex items-center gap-3">
        <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
          <MapPin className="w-5 h-5" />
        </span>
        <div>
          <h1 className="text-2xl font-bold">Análise por Bairro</h1>
          <p className="text-sm text-muted-foreground">
            Votos de um candidato distribuídos por bairro da cidade (TSE).
          </p>
        </div>
      </header>

      {/* Passo 1: UF + cargo + municipio */}
      <section className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-4">
        <Select
          label="UF"
          value={state}
          onChange={(v) => {
            setState(v);
            setMuni(null);
            setCandidate(null);
          }}
          options={TSE_STATES.map((s) => ({ value: s, label: s }))}
          className="md:col-span-2"
        />
        <Select
          label="Cargo"
          value={office}
          onChange={(v) => {
            setOffice(v);
            setCandidate(null);
          }}
          options={OFFICES}
          className="md:col-span-3"
        />
        <div className="md:col-span-7">
          <MunicipalityPicker
            state={state}
            muni={muni}
            onPick={(m) => {
              setMuni(m);
              setCandidate(null);
            }}
            onClear={() => {
              setMuni(null);
              setCandidate(null);
            }}
          />
        </div>
      </section>

      {/* Passo 2: candidato */}
      {muni && !candidate && (
        <CandidatePicker
          muni={muni}
          office={office}
          onPick={setCandidate}
        />
      )}

      {/* Passo 3: resultado por bairro */}
      {muni && candidate && (
        <NeighborhoodResult
          candidate={candidate}
          muni={muni}
          onBack={() => setCandidate(null)}
        />
      )}

      {!muni && (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
          <Search className="mx-auto h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground mt-3">
            Escolha UF + cargo e busque a cidade pra começar.
          </p>
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------- municipio picker

function MunicipalityPicker({
  state,
  muni,
  onPick,
  onClear,
}: {
  state: string;
  muni: TseMunicipality | null;
  onPick: (m: TseMunicipality) => void;
  onClear: () => void;
}) {
  const [search, setSearch] = useState("");
  const debounced = useDebounce(search, 300);
  const [items, setItems] = useState<TseMunicipality[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (muni) return;
    const q = debounced.trim();
    if (q.length < 2) {
      setItems([]);
      return;
    }
    setLoading(true);
    const p = new URLSearchParams({ limit: "30", search: q, state });
    api<Page<TseMunicipality>>(`/v1/tse/municipalities?${p.toString()}`)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [debounced, state, muni]);

  if (muni) {
    return (
      <div>
        <label className="text-xs uppercase tracking-wider text-muted-foreground">
          Município
        </label>
        <div className="mt-1 flex items-center justify-between gap-2 py-2 px-3 rounded-md bg-card border border-primary/40">
          <span className="font-semibold">
            {muni.name}{" "}
            <span className="text-muted-foreground font-normal">/{muni.state}</span>
          </span>
          <button
            onClick={onClear}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Trocar"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-muted-foreground">
        Município
      </label>
      <div className="relative mt-1">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar município…"
          className="w-full pl-9 py-2 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
      {(loading || items.length > 0) && (
        <div className="mt-1 rounded-md border bg-card divide-y divide-border max-h-60 overflow-auto absolute z-20 w-[calc(100%-1.5rem)] md:w-auto md:min-w-[300px] shadow-lg">
          {loading && (
            <div className="p-3 text-center text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> buscando…
            </div>
          )}
          {items.map((m) => (
            <button
              key={m.id}
              onClick={() => {
                onPick(m);
                setItems([]);
                setSearch("");
              }}
              className="w-full text-left p-2.5 hover:bg-accent/50 text-sm flex justify-between"
            >
              <span className="font-medium">{m.name}</span>
              <span className="text-xs text-muted-foreground">{m.state}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------- candidate picker

function CandidatePicker({
  muni,
  office,
  onPick,
}: {
  muni: TseMunicipality;
  office: string;
  onPick: (c: TseCandidate) => void;
}) {
  // Reusa o ranking do municipio (ja ordenado por votos) como lista de escolha
  const [items, setItems] = useState<TseCandidate[] | null>(null);
  const [search, setSearch] = useState("");
  const debounced = useDebounce(search, 300);

  useEffect(() => {
    const p = new URLSearchParams({
      state: muni.state,
      office_code: office,
      limit: "30",
    });
    if (debounced.trim()) p.set("search", debounced.trim());
    api<Page<TseCandidate>>(`/v1/tse/candidates?${p.toString()}`)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [muni.state, office, debounced]);

  return (
    <div>
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Buscar candidato em ${muni.name}…`}
          className="w-full pl-9 py-2 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
      <div className="rounded-lg border bg-card divide-y divide-border max-h-[60vh] overflow-auto">
        {items === null && (
          <div className="p-8 text-center">
            <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
          </div>
        )}
        {items?.length === 0 && (
          <div className="p-8 text-center text-sm text-muted-foreground">
            Nenhum candidato encontrado.
          </div>
        )}
        {items?.map((c) => (
          <button
            key={c.id}
            onClick={() => onPick(c)}
            className="w-full text-left p-3 hover:bg-accent/50 flex items-center gap-3"
          >
            <CandidatePhoto
              candidateId={c.id}
              name={c.urn_name}
              partyNumber={c.party.number}
              size="sm"
            />
            <div className="flex-1 min-w-0">
              <p className="font-semibold truncate flex items-center gap-2">
                <span className="text-primary font-mono">{c.number}</span>
                <span className="truncate">{c.urn_name}</span>
                <ResultBadge status={c.result_status} size="sm" />
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {c.party.abbreviation} · {c.office_name}
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ----------------------------------------------------- result

function NeighborhoodResult({
  candidate,
  muni,
  onBack,
}: {
  candidate: TseCandidate;
  muni: TseMunicipality;
  onBack: () => void;
}) {
  const [data, setData] = useState<TseCandidateByNeighborhoodResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api<TseCandidateByNeighborhoodResponse>(
      `/v1/tse/candidates/${candidate.id}/by-neighborhood?municipality_id=${muni.id}`,
    )
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [candidate.id, muni.id]);

  const maxVotes = data?.items[0]?.votes ?? 1;

  return (
    <div>
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-3"
      >
        <ArrowLeft className="w-4 h-4" /> Trocar candidato
      </button>

      {/* Header candidato */}
      <div className="flex items-center gap-3 mb-4 rounded-lg border bg-card p-3">
        <CandidatePhoto
          candidateId={candidate.id}
          name={candidate.urn_name}
          partyNumber={candidate.party.number}
          size="md"
        />
        <div className="flex-1 min-w-0">
          <p className="font-bold truncate flex items-center gap-2">
            {candidate.urn_name}
            <ResultBadge status={candidate.result_status} size="sm" />
          </p>
          <p className="text-xs text-muted-foreground">
            {candidate.party.abbreviation} · {candidate.number} ·{" "}
            {candidate.office_name} · {muni.name}/{muni.state}
          </p>
        </div>
        {data && (
          <div className="text-right shrink-0">
            <p className="text-xl font-bold text-primary">
              {numberFmt.format(data.total_votes)}
            </p>
            <p className="text-xs text-muted-foreground">
              {data.total_neighborhoods} bairros
            </p>
          </div>
        )}
      </div>

      {loading ? (
        <div className="py-16 text-center">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
          <p className="text-lg font-semibold">Dados de bairro indisponíveis</p>
          <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
            A votação por seção de <strong>{muni.state}</strong> ainda não foi
            sincronizada. Por enquanto só MG está disponível; os demais estados
            estão sendo importados.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* Ranking bairros */}
          <div className="lg:col-span-2">
            <ul className="rounded-lg border bg-card divide-y divide-border max-h-[60vh] overflow-auto">
              {data.items.map((n, i) => {
                const pct = (n.votes / maxVotes) * 100;
                return (
                  <li key={n.neighborhood} className="p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-sm truncate">
                        {i + 1}. {n.neighborhood}
                      </span>
                      <span className="font-mono font-bold text-sm shrink-0">
                        {numberFmt.format(n.votes)}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-primary"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {n.places_count} local(is)
                    </p>
                  </li>
                );
              })}
            </ul>
          </div>
          {/* Mapa */}
          <div className="lg:col-span-3">
            <div className="h-[60vh] rounded-lg border border-border overflow-hidden">
              <CandidateNeighborhoodMap data={data} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------- helpers

function Select({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function MapBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full w-full grid place-items-center text-muted-foreground">
      {children}
    </div>
  );
}
