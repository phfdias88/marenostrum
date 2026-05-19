"use client";

/**
 * Analise por Partidos (estilo Politique).
 * - Grid com os 29 partidos
 * - Clique em um -> mostra os candidatos do partido (filtravel por UF/cargo)
 */
import { ArrowLeft, ArrowRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { Page, TseCandidate, TseParty } from "@/lib/types";
import { TSE_OFFICES, TSE_STATES } from "@/lib/types";
import { PartyLogo } from "@/components/tse/PartyLogo";

const numberFmt = new Intl.NumberFormat("pt-BR");

export default function PartidosAnalysisPage() {
  const [parties, setParties] = useState<TseParty[] | null>(null);
  const [selected, setSelected] = useState<TseParty | null>(null);

  useEffect(() => {
    api<TseParty[]>("/v1/tse/parties").then(setParties).catch(() => setParties([]));
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Análises
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-bold">Análise por Partidos</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {parties === null
            ? "Carregando…"
            : `${parties.length} partidos importados do TSE 2024.`}
        </p>
      </header>

      {selected ? (
        <PartyDrillDown party={selected} onBack={() => setSelected(null)} />
      ) : (
        <PartyGrid parties={parties} onSelect={setSelected} />
      )}
    </div>
  );
}

// ----------------------------------------------------------------- grid

function PartyGrid({
  parties,
  onSelect,
}: {
  parties: TseParty[] | null;
  onSelect: (p: TseParty) => void;
}) {
  if (parties === null) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            className="h-24 rounded-lg border bg-card/60 animate-pulse"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {parties
        .slice()
        .sort((a, b) => a.number - b.number)
        .map((p) => (
          <button
            key={p.id}
            onClick={() => onSelect(p)}
            className="text-left rounded-lg border bg-card p-4 hover:border-primary/60 hover:bg-card/80 transition-all hover:-translate-y-0.5"
          >
            <div className="flex items-center gap-3">
              <PartyLogo
                number={p.number}
                abbreviation={p.abbreviation}
                size="md"
              />
              <div className="min-w-0">
                <p className="font-bold">{p.abbreviation}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {p.name}
                </p>
              </div>
            </div>
          </button>
        ))}
    </div>
  );
}

// ----------------------------------------------------------------- drill-down

const PAGE_SIZE = 25;

function PartyDrillDown({
  party,
  onBack,
}: {
  party: TseParty;
  onBack: () => void;
}) {
  const [state, setState] = useState<string>("");
  const [office, setOffice] = useState<string>("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<Page<TseCandidate> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => setPage(0), [state, office]);

  useEffect(() => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
      party_number: String(party.number),
    });
    if (state) params.set("state", state);
    if (office) params.set("office_code", office);

    setLoading(true);
    api<Page<TseCandidate>>(`/v1/tse/candidates?${params.toString()}`)
      .then(setData)
      .catch(() =>
        setData({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 }),
      )
      .finally(() => setLoading(false));
  }, [party.number, state, office, page]);

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div>
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Todos os partidos
      </button>

      <div className="flex items-center gap-4 mb-6">
        <PartyLogo
          number={party.number}
          abbreviation={party.abbreviation}
          size="lg"
        />
        <div>
          <h2 className="text-2xl font-bold">{party.abbreviation}</h2>
          <p className="text-sm text-muted-foreground">{party.name}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-5">
        <Select
          label="UF"
          value={state}
          onChange={setState}
          options={[
            { value: "", label: "Todas" },
            ...TSE_STATES.map((s) => ({ value: s, label: s })),
          ]}
          className="md:col-span-3"
        />
        <Select
          label="Cargo"
          value={office}
          onChange={setOffice}
          options={[
            { value: "", label: "Todos" },
            ...Object.entries(TSE_OFFICES).map(([k, v]) => ({
              value: k,
              label: v,
            })),
          ]}
          className="md:col-span-4"
        />
      </div>

      <div className="text-sm text-muted-foreground mb-2">
        {loading ? (
          <span className="inline-flex items-center gap-2">
            <Loader2 className="w-3 h-3 animate-spin" /> carregando…
          </span>
        ) : (
          `${numberFmt.format(total)} candidato(s) do ${party.abbreviation}`
        )}
      </div>

      <div className="rounded-lg border bg-card divide-y divide-border">
        {data?.items.length === 0 && !loading && (
          <div className="p-10 text-center text-sm text-muted-foreground">
            Nenhum candidato com esses filtros.
          </div>
        )}
        {data?.items.map((c) => (
          <Link
            key={c.id}
            href={`/dashboard/analises/candidato?focus=${c.id}`}
            className="flex items-center gap-4 p-4 hover:bg-accent/50 transition-colors"
          >
            <span className="grid place-items-center w-10 h-10 rounded-md bg-primary/10 text-primary font-bold text-sm shrink-0">
              {c.number}
            </span>
            <div className="flex-1 min-w-0">
              <p className="font-semibold truncate">{c.urn_name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {c.name} · {c.office_name} · {c.state}
              </p>
            </div>
            <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0" />
          </Link>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-3 text-sm">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0 || loading}
            className="text-muted-foreground hover:text-foreground disabled:opacity-40"
          >
            ← Anterior
          </button>
          <span className="text-muted-foreground">
            Página {page + 1} de {numberFmt.format(totalPages)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={page + 1 >= totalPages || loading}
            className="text-muted-foreground hover:text-foreground disabled:opacity-40"
          >
            Próxima →
          </button>
        </div>
      )}
    </div>
  );
}

// -------------------------------------------------------------- shared

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
        className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border
                   focus:outline-none focus:ring-2 focus:ring-primary/30"
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
