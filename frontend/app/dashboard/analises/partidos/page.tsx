"use client";

/**
 * Analise por Partidos (estilo Politique).
 * - Grid com os 29 partidos
 * - Clique em um -> mostra os candidatos do partido (filtravel por UF/cargo)
 */
import { ArrowLeft, ArrowRight, BarChart3, Grid3x3, Loader2, Trophy } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type {
  Page,
  TseCandidate,
  TseParty,
  TsePartyPerformanceResponse,
} from "@/lib/types";
import { TSE_OFFICES, TSE_STATES } from "@/lib/types";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { CandidateListSkeleton } from "@/components/tse/Skeletons";

const numberFmt = new Intl.NumberFormat("pt-BR");

type Tab = "desempenho" | "lista";

export default function PartidosAnalysisPage() {
  const [parties, setParties] = useState<TseParty[] | null>(null);
  const [selected, setSelected] = useState<TseParty | null>(null);
  const [tab, setTab] = useState<Tab>("desempenho");

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

      <header className="mb-6 flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Análise por Partidos</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Desempenho eleitoral (eleitos + votos) e candidatos por partido.
          </p>
        </div>
        {!selected && (
          <div className="flex gap-1 bg-card border border-border rounded-md p-0.5">
            <TabBtn active={tab === "desempenho"} onClick={() => setTab("desempenho")} icon={<BarChart3 className="w-4 h-4" />} label="Desempenho" />
            <TabBtn active={tab === "lista"} onClick={() => setTab("lista")} icon={<Grid3x3 className="w-4 h-4" />} label="Lista" />
          </div>
        )}
      </header>

      {selected ? (
        <PartyDrillDown party={selected} onBack={() => setSelected(null)} />
      ) : tab === "desempenho" ? (
        <PartyPerformance onSelect={setSelected} parties={parties} />
      ) : (
        <PartyGrid parties={parties} onSelect={setSelected} />
      )}
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
        active ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

// ----------------------------------------------------------------- desempenho

const PERF_OFFICES: Record<string, { value: string; label: string }[]> = {
  "2024": [
    { value: "11", label: "Prefeito" },
    { value: "13", label: "Vereador" },
  ],
  "2022": [
    { value: "3", label: "Governador" },
    { value: "5", label: "Senador" },
    { value: "6", label: "Deputado Federal" },
    { value: "7", label: "Deputado Estadual" },
  ],
};

function PartyPerformance({
  onSelect,
  parties,
}: {
  onSelect: (p: TseParty) => void;
  parties: TseParty[] | null;
}) {
  const [year, setYear] = useState("2024");
  const [office, setOffice] = useState("11");
  const [state, setState] = useState("");
  const [data, setData] = useState<TsePartyPerformanceResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ year, office_code: office });
    if (state) p.set("state", state);
    api<TsePartyPerformanceResponse>(`/v1/tse/stats/party-performance?${p.toString()}`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [year, office, state]);

  const partyByNumber = useMemo(() => {
    const m = new Map<number, TseParty>();
    (parties ?? []).forEach((p) => m.set(p.number, p));
    return m;
  }, [parties]);

  const ranked = (data?.items ?? []).filter((i) => i.elected_count > 0 || i.total_votes > 0);
  const maxElected = Math.max(1, ...ranked.map((i) => i.elected_count));

  return (
    <div>
      <section className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-5">
        <Select
          label="Ano"
          value={year}
          onChange={(v) => {
            setYear(v);
            setOffice(PERF_OFFICES[v][0].value);
          }}
          options={[
            { value: "2024", label: "2024 (Municipal)" },
            { value: "2022", label: "2022 (Federal/Estadual)" },
          ]}
          className="md:col-span-3"
        />
        <Select
          label="Cargo"
          value={office}
          onChange={setOffice}
          options={PERF_OFFICES[year]}
          className="md:col-span-4"
        />
        <Select
          label="UF"
          value={state}
          onChange={setState}
          options={[
            { value: "", label: "Brasil (todas)" },
            ...TSE_STATES.map((s) => ({ value: s, label: s })),
          ]}
          className="md:col-span-2"
        />
      </section>

      {loading ? (
        <CandidateListSkeleton rows={8} />
      ) : !data || ranked.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-10">
          Sem dados para esse filtro.
        </p>
      ) : (
        <>
          <div className="flex gap-3 mb-4">
            <div className="rounded-lg border bg-card/60 px-4 py-2">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Total eleitos</p>
              <p className="text-2xl font-bold text-primary">{numberFmt.format(data.total_elected)}</p>
            </div>
            <div className="rounded-lg border bg-card/60 px-4 py-2">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Votos nominais</p>
              <p className="text-2xl font-bold">{numberFmt.format(data.total_votes)}</p>
            </div>
          </div>

          <div className="rounded-lg border bg-card divide-y divide-border">
            {ranked.map((i, idx) => {
              const party = partyByNumber.get(i.party.number) ?? i.party;
              const pct = (i.elected_count / maxElected) * 100;
              return (
                <button
                  key={i.party.id}
                  onClick={() => onSelect(party)}
                  className="w-full text-left p-3 hover:bg-accent/40 flex items-center gap-3"
                >
                  <span className="w-6 text-center text-sm font-bold text-muted-foreground">
                    {idx + 1}
                  </span>
                  <PartyLogo number={i.party.number} abbreviation={i.party.abbreviation} size="sm" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold">{i.party.abbreviation}</span>
                      <span className="text-sm">
                        <strong className="text-primary">{numberFmt.format(i.elected_count)}</strong>
                        <span className="text-muted-foreground"> eleitos</span>
                      </span>
                    </div>
                    <div className="mt-1.5 h-2 rounded-full bg-muted overflow-hidden">
                      <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {numberFmt.format(i.total_votes)} votos · {numberFmt.format(i.candidates_count)} candidatos
                    </p>
                  </div>
                  <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0" />
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

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
      <label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</label>
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
          <Link
            href={`/dashboard/analises/partido/${party.number}`}
            className="mt-1 inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
          >
            Abrir página completa →
          </Link>
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
            href={`/dashboard/analises/candidato/${c.id}`}
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

