"use client";

/**
 * Análise por Zona Eleitoral — /dashboard/analises/zona.
 * Escolhe um município (busca + UF) → vê os candidatos mais votados em cada
 * zona eleitoral, por cargo/ano. Usa /municipalities/{id}/zones.
 */
import { ArrowLeft, Compass, Loader2, MapPin, Search, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  Page,
  TseMunicipality,
  TseMunicipalityZones,
} from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { StateFlag } from "@/components/tse/StateFlag";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { CandidateListSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";

const numberFmt = new Intl.NumberFormat("pt-BR");
const pctFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

const OFFICES_BY_YEAR: Record<string, { value: string; label: string }[]> = {
  "2024": [
    { value: "11", label: "Prefeito" },
    { value: "13", label: "Vereador" },
  ],
};

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export default function ZonaAnalysisPage() {
  const [selected, setSelected] = useState<TseMunicipality | null>(null);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-6 flex items-center gap-3">
        <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
          <Compass className="w-5 h-5" />
        </span>
        <div>
          <h1
            className="text-2xl font-bold"
            title="Zona eleitoral = divisão administrativa do TSE dentro do município."
          >
            Zona eleitoral
          </h1>
          <p className="text-sm text-muted-foreground">
            Candidatos mais votados em cada zona de uma cidade · eleição municipal
            de 2024.
          </p>
        </div>
      </header>

      {selected ? (
        <ZoneDrill muni={selected} onBack={() => setSelected(null)} />
      ) : (
        <MunicipalityPicker onPick={setSelected} />
      )}
    </div>
  );
}

function MunicipalityPicker({ onPick }: { onPick: (m: TseMunicipality) => void }) {
  const [state, setState] = useState("");
  const [search, setSearch] = useState("");
  const debounced = useDebounce(search, 300);
  const [data, setData] = useState<Page<TseMunicipality> | null>(null);
  const [loading, setLoading] = useState(true);

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

  return (
    <div>
      <section className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-4">
        <div className="md:col-span-3">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">UF</label>
          <select
            value={state}
            onChange={(e) => setState(e.target.value)}
            className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            <option value="">Todas</option>
            {TSE_STATES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="md:col-span-9">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">Cidade</label>
          <div className="relative mt-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Nome do município…"
              className="w-full pl-9 pr-9 py-2 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </section>

      {loading && !data ? (
        <CandidateListSkeleton rows={6} />
      ) : data?.items.length === 0 ? (
        <div className="rounded-lg border bg-card">
          <EmptyState icon={MapPin} title="Nenhuma cidade com esse filtro" hint="Tente outra UF ou nome." />
        </div>
      ) : (
        <div className="rounded-lg border bg-card divide-y divide-border">
          {data?.items.map((m) => (
            <button
              key={m.id}
              onClick={() => onPick(m)}
              className="w-full text-left p-4 hover:bg-accent/50 transition-colors flex items-center gap-4"
            >
              <StateFlag uf={m.state} size="md" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold truncate">{m.name}</p>
                <p className="text-xs text-muted-foreground">{m.state} · TSE {m.tse_code}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ZoneDrill({ muni, onBack }: { muni: TseMunicipality; onBack: () => void }) {
  const [year, setYear] = useState("2024");
  const [office, setOffice] = useState("11");
  const [data, setData] = useState<TseMunicipalityZones | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ year, office_code: office, top_per_zone: "5" });
    api<TseMunicipalityZones>(`/v1/tse/municipalities/${muni.id}/zones?${p.toString()}`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [muni.id, year, office]);

  return (
    <div>
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Outra cidade
      </button>

      <div className="flex items-center gap-4 mb-5">
        <StateFlag uf={muni.state} size="lg" className="!w-16 !h-11 shadow" />
        <div className="flex-1">
          <h2 className="text-2xl font-bold">{muni.name}</h2>
          <p className="text-sm text-muted-foreground">
            {muni.state} · TSE {muni.tse_code}
          </p>
          <Link
            href={`/dashboard/analises/municipio/${muni.id}`}
            className="mt-1 inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
          >
            Abrir página completa →
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <Select label="Cargo" value={office} onChange={setOffice} options={OFFICES_BY_YEAR[year]} />
      </div>

      {loading ? (
        <CandidateListSkeleton rows={8} />
      ) : !data || data.zones.length === 0 ? (
        <div className="rounded-lg border bg-card">
          <EmptyState icon={Compass} title="Sem dados de zona pra esse filtro" hint="Tente outro cargo." />
        </div>
      ) : (
        <>
          <p className="text-xs text-muted-foreground mb-2">
            {data.zones.length} zona(s) · {data.office_name}
          </p>
          <div className="space-y-2">
            {data.zones.map((z) => (
              <div key={z.zone} className="rounded-lg border bg-card p-3 mn-hover">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm">Zona {z.zone}</span>
                  <span className="text-xs text-muted-foreground font-mono">
                    {numberFmt.format(z.total_votes)} votos na zona (todos os candidatos) · top 5 exibidos
                  </span>
                </div>
                <ol className="space-y-1">
                  {z.candidates.map((c, i) => {
                    const pct = z.total_votes > 0 ? (c.votes / z.total_votes) * 100 : 0;
                    return (
                      <li key={c.candidate.id} className="flex items-center gap-2 text-sm">
                        <span className="w-4 text-center text-xs text-muted-foreground shrink-0">
                          {i + 1}
                        </span>
                        <CandidatePhoto
                          candidateId={c.candidate.id}
                          name={c.candidate.urn_name}
                          partyNumber={c.candidate.party.number}
                          size="sm"
                        />
                        <Link
                          href={`/dashboard/analises/candidato/${c.candidate.id}`}
                          className="flex-1 min-w-0 truncate hover:underline flex items-center gap-1.5"
                        >
                          <span className="truncate">{c.candidate.urn_name}</span>
                          <span className="text-muted-foreground">
                            ({c.candidate.party.abbreviation})
                          </span>
                          <ResultBadge status={c.candidate.result_status} size="sm" />
                        </Link>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {pctFmt.format(pct)}%
                        </span>
                        <span className="font-mono font-semibold shrink-0 w-16 text-right">
                          {numberFmt.format(c.votes)}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              </div>
            ))}
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
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}
