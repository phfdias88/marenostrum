"use client";

/**
 * Página dedicada do município — /dashboard/analises/municipio/{id}.
 * URL compartilhável: bandeira, nome, top candidatos por cargo/ano com % dos
 * votos nominais, favoritar e exportar. Espelha as páginas de candidato/partido.
 */
import { ArrowLeft, SearchX, Users } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { TseElectorate, TseMunicipalityResults } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { StateFlag } from "@/components/tse/StateFlag";
import { FavoriteStar } from "@/components/tse/FavoriteStar";
import { ExportShare } from "@/components/tse/ExportShare";
import { CandidateListSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";

const numberFmt = new Intl.NumberFormat("pt-BR");
const pctFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

const OFFICES_BY_YEAR: Record<string, { value: string; label: string }[]> = {
  "2024": [
    { value: "11", label: "Prefeito" },
    { value: "13", label: "Vereador" },
  ],
  "2022": [
    { value: "3", label: "Governador" },
    { value: "5", label: "Senador" },
    { value: "6", label: "Deputado Federal" },
    { value: "7", label: "Deputado Estadual" },
    { value: "1", label: "Presidente" },
  ],
};

export default function MunicipioDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [year, setYear] = useState("2024");
  const [office, setOffice] = useState("11");
  const [data, setData] = useState<TseMunicipalityResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [electorate, setElectorate] = useState<TseElectorate | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  // Perfil do eleitorado (independe do filtro ano/cargo). 404 = não sincronizado.
  useEffect(() => {
    if (!id) return;
    api<TseElectorate>(`/v1/tse/municipalities/${id}/electorate`)
      .then(setElectorate)
      .catch(() => setElectorate(null));
  }, [id]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(false);
    const p = new URLSearchParams({ limit: "30", year });
    if (office) p.set("office_code", office);
    api<TseMunicipalityResults>(
      `/v1/tse/municipalities/${id}/top-candidates?${p.toString()}`,
    )
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [id, year, office]);

  const muni = data?.municipality;
  const maxVotes = data?.results[0]?.votes ?? 1;
  const totalVotes = data?.total_votes ?? 0;

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-16">
        <EmptyState icon={SearchX} title="Município não encontrado" />
        <div className="text-center">
          <Link href="/dashboard/analises/municipios" className="text-primary hover:underline text-sm">
            ← Voltar aos municípios
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/dashboard/analises/municipios"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Municípios
        </Link>
        {muni && (
          <div className="flex items-center gap-3" data-html2canvas-ignore>
            <FavoriteStar
              fav={{
                kind: "municipality",
                id: muni.id,
                label: muni.name,
                sub: muni.state,
                state: muni.state,
              }}
              size={20}
            />
            <ExportShare
              targetRef={cardRef}
              filename={`municipio-${muni.name}`.toLowerCase().replace(/[^a-z0-9]+/g, "-")}
            />
          </div>
        )}
      </div>

      <div ref={cardRef} className="bg-background rounded-xl">
        {/* Hero */}
        <div className="rounded-xl border bg-card p-6 flex items-center gap-5">
          {muni ? (
            <StateFlag uf={muni.state} size="lg" className="!w-16 !h-11 shadow shrink-0" />
          ) : (
            <div className="w-16 h-11 rounded bg-muted animate-pulse shrink-0" />
          )}
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              {muni ? `${muni.state} · TSE ${muni.tse_code}` : "…"}
            </p>
            <h1 className="text-2xl font-bold">{muni?.name ?? "…"}</h1>
          </div>
        </div>

        {/* Filtros */}
        <section className="grid grid-cols-2 md:grid-cols-12 gap-3 mt-4" data-html2canvas-ignore>
          <Select
            label="Ano"
            value={year}
            onChange={(v) => {
              setYear(v);
              setOffice(OFFICES_BY_YEAR[v][0].value);
            }}
            options={[
              { value: "2024", label: "2024 (Municipal)" },
              { value: "2022", label: "2022 (Federal/Estadual)" },
            ]}
            className="md:col-span-5"
          />
          <Select
            label="Cargo"
            value={office}
            onChange={setOffice}
            options={OFFICES_BY_YEAR[year]}
            className="md:col-span-7"
          />
        </section>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 mt-4">
          <Stat label="Votos nominais (cargo)" value={loading ? null : totalVotes} accent="text-primary" />
          <Stat label="Candidatos com votos" value={loading ? null : data?.total_results ?? 0} />
        </div>

        {/* Perfil do eleitorado (TSE) */}
        {electorate && (
          <div className="mt-6">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> Perfil do eleitorado ·{" "}
              {numberFmt.format(electorate.total)} eleitores ({electorate.year})
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Breakdown title="Gênero" data={electorate.by_gender} total={electorate.total} />
              <Breakdown title="Faixa etária" data={electorate.by_age} total={electorate.total} />
              <Breakdown title="Escolaridade" data={electorate.by_education} total={electorate.total} />
            </div>
          </div>
        )}

        {/* Top candidatos */}
        <div className="mt-6">
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5" /> Mais votados aqui — {data?.office_name ?? "cargo"}
          </p>
          {loading ? (
            <CandidateListSkeleton rows={6} />
          ) : !data || data.results.length === 0 ? (
            <div className="rounded-lg border bg-card">
              <EmptyState
                icon={SearchX}
                title="Sem votação pra esse filtro"
                hint="Tente outro ano ou cargo neste município."
              />
            </div>
          ) : (
            <ol className="rounded-lg border bg-card divide-y divide-border">
              {data.results.map((r, i) => {
                const pct = totalVotes > 0 ? (r.votes / totalVotes) * 100 : 0;
                return (
                  <li key={r.candidate.id}>
                    <Link
                      href={`/dashboard/analises/candidato/${r.candidate.id}`}
                      className="p-3 flex items-center gap-3 hover:bg-accent/50 transition-colors"
                    >
                      <span className="w-6 text-center font-bold text-muted-foreground">
                        {i + 1}
                      </span>
                      <CandidatePhoto
                        candidateId={r.candidate.id}
                        name={r.candidate.urn_name}
                        partyNumber={r.candidate.party.number}
                        size="sm"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold truncate flex items-center gap-2">
                          <span className="text-primary font-mono">{r.candidate.number}</span>
                          <span className="truncate">{r.candidate.urn_name}</span>
                          <ResultBadge status={r.candidate.result_status} size="sm" />
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          {r.candidate.party.abbreviation}
                          {totalVotes > 0 && ` · ${pctFmt.format(pct)}%`}
                        </p>
                        <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className="h-full bg-primary"
                            style={{ width: `${(r.votes / maxVotes) * 100}%` }}
                          />
                        </div>
                      </div>
                      <span className="font-mono font-bold tabular-nums shrink-0">
                        {numberFmt.format(r.votes)}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}

function Breakdown({
  title,
  data,
  total,
}: {
  title: string;
  data: Record<string, number>;
  total: number;
}) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2.5">{title}</p>
      <ul className="space-y-2">
        {entries.map(([label, value]) => {
          const pct = total > 0 ? (value / total) * 100 : 0;
          return (
            <li key={label}>
              <div className="flex items-center justify-between text-xs mb-0.5">
                <span className="truncate">{label}</span>
                <span className="text-muted-foreground font-mono shrink-0">
                  {pctFmt.format(pct)}%
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full bg-primary"
                  style={{ width: `${(value / max) * 100}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | null;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border bg-card/60 p-4 text-center">
      {value === null ? (
        <div className="h-8 w-20 mx-auto rounded bg-muted animate-pulse" />
      ) : (
        <p className={`text-2xl font-bold ${accent ?? ""}`}>{numberFmt.format(value)}</p>
      )}
      <p className="text-xs text-muted-foreground mt-1">{label}</p>
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
