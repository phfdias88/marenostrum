"use client";

/**
 * Página dedicada do município — /dashboard/analises/municipio/{id}.
 * URL compartilhável: bandeira, nome, top candidatos por cargo/ano com % dos
 * votos nominais, favoritar e exportar. Espelha as páginas de candidato/partido.
 */
import { ArrowLeft, Crown, History, SearchX, Users } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type {
  TseElectorate,
  TseMunicipalityResults,
  TseMunicipalityTimeline,
  TseMunicipalityZones,
} from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { StateFlag } from "@/components/tse/StateFlag";
import { FavoriteStar } from "@/components/tse/FavoriteStar";
import { ExportShare } from "@/components/tse/ExportShare";
import { CandidateListSkeleton } from "@/components/tse/Skeletons";
import { EmptyState } from "@/components/tse/EmptyState";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";

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
  const [zones, setZones] = useState<TseMunicipalityZones | null>(null);
  const [timeline, setTimeline] = useState<TseMunicipalityTimeline | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  // Perfil do eleitorado (independe do filtro ano/cargo). 404 = não sincronizado.
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setElectorate(null);
    api<TseElectorate>(`/v1/tse/municipalities/${id}/electorate`)
      .then((d) => { if (!cancelled) setElectorate(d); })
      .catch(() => { if (!cancelled) setElectorate(null); });
    return () => { cancelled = true; };
  }, [id]);

  // Timeline eleitoral (independe do filtro — todos os anos/cargos)
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setTimeline(null);
    api<TseMunicipalityTimeline>(`/v1/tse/municipalities/${id}/timeline`)
      .then((d) => { if (!cancelled) setTimeline(d); })
      .catch(() => { if (!cancelled) setTimeline(null); });
    return () => { cancelled = true; };
  }, [id]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    setData(null); // reset pra nao mostrar dados antigos durante navegacao
    const p = new URLSearchParams({ limit: "30", year });
    if (office) p.set("office_code", office);
    api<TseMunicipalityResults>(
      `/v1/tse/municipalities/${id}/top-candidates?${p.toString()}`,
    )
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id, year, office]);

  // Top candidatos por zona (404/vazio = zona nao sincronizada → esconde)
  useEffect(() => {
    if (!id || !office) {
      setZones(null);
      return;
    }
    let cancelled = false;
    setZones(null);
    const p = new URLSearchParams({ year, office_code: office, top_per_zone: "5" });
    api<TseMunicipalityZones>(`/v1/tse/municipalities/${id}/zones?${p.toString()}`)
      .then((d) => { if (!cancelled) setZones(d); })
      .catch(() => { if (!cancelled) setZones(null); });
    return () => { cancelled = true; };
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
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-8">
      <div className="flex items-center justify-between gap-2 mb-4 flex-wrap">
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
        <div className="rounded-xl border bg-gradient-to-br from-primary/10 via-card to-card p-4 sm:p-6 flex items-center gap-3 sm:gap-5">
          {muni ? (
            <StateFlag uf={muni.state} size="lg" className="!w-12 sm:!w-16 !h-8 sm:!h-11 shadow shrink-0" />
          ) : (
            <div className="w-12 sm:w-16 h-8 sm:h-11 rounded bg-muted animate-pulse shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-[10px] sm:text-xs uppercase tracking-wider text-muted-foreground">
              {muni ? `${muni.state} · TSE ${muni.tse_code}` : "…"}
            </p>
            <h1 className="text-lg sm:text-2xl font-bold leading-tight truncate">{muni?.name ?? "…"}</h1>
          </div>
          {electorate && (
            <div className="hidden sm:block text-right shrink-0">
              <p className="text-2xl font-bold text-primary tabular-nums">
                {numberFmt.format(electorate.total)}
              </p>
              <p className="text-xs text-muted-foreground">eleitores</p>
            </div>
          )}
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
          <Stat
            label="Votos nominais (cargo)"
            value={loading ? null : totalVotes}
            accent="text-primary"
            hint={["11", "1", "3"].includes(office) ? "soma 1º + 2º turno (quando houve)" : undefined}
          />
          <Stat label="Candidatos com votos" value={loading ? null : data?.total_results ?? 0} />
        </div>

        {/* Perfil do eleitorado (TSE) */}
        {electorate && (
          <div className="mt-6 mn-fade-in">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> Perfil do eleitorado ·{" "}
              {numberFmt.format(electorate.total)} eleitores ({electorate.year})
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Breakdown title="Gênero" data={electorate.by_gender} total={electorate.total} palette={PAL_GENDER} />
              <Breakdown title="Faixa etária" data={electorate.by_age} total={electorate.total} palette={PAL_AGE} />
              <Breakdown title="Escolaridade" data={electorate.by_education} total={electorate.total} palette={PAL_EDU} />
            </div>
          </div>
        )}

        {/* Linha do tempo eleitoral (independe do filtro) */}
        {timeline && timeline.items.length > 0 && (
          <div className="mt-6 mn-fade-in">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <History className="w-3.5 h-3.5" /> Linha do tempo eleitoral · vencedores por cargo/ano
            </p>
            <TimelineGrid items={timeline.items} />
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

        {/* Top candidatos por zona eleitoral */}
        {zones && zones.zones.length > 0 && (
          <div className="mt-6 mn-fade-in">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> Por zona eleitoral · {zones.office_name ?? "cargo"}
              <span className="text-muted-foreground/70">({zones.zones.length} zonas)</span>
            </p>
            <div className="space-y-2">
              {zones.zones.map((z) => (
                <div key={z.zone} className="rounded-lg border bg-card p-3 mn-hover">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-sm">Zona {z.zone}</span>
                    <span className="text-xs text-muted-foreground font-mono">
                      {numberFmt.format(z.total_votes)} votos
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
                          <Link
                            href={`/dashboard/analises/candidato/${c.candidate.id}`}
                            className="flex-1 min-w-0 truncate hover:underline"
                          >
                            <span className="text-primary font-mono">{c.candidate.number}</span>{" "}
                            {c.candidate.urn_name}{" "}
                            <span className="text-muted-foreground">
                              ({c.candidate.party.abbreviation})
                            </span>
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
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================ Timeline

// Detecta se um cargo teve mais de 1 turno no ano (pra rotular "1º turno" / "2º turno")
function hasMultiRounds(yearItems: import("@/lib/types").TseTimelineItem[], officeCode: number): boolean {
  return yearItems.filter((x) => x.office_code === officeCode).length > 1;
}

function TimelineGrid({ items }: { items: import("@/lib/types").TseTimelineItem[] }) {
  // Agrupa por ano (desc) → dentro do ano, lista cargos
  const byYear = new Map<number, typeof items>();
  for (const it of items) {
    const arr = byYear.get(it.year) ?? [];
    arr.push(it);
    byYear.set(it.year, arr);
  }
  const years = Array.from(byYear.keys()).sort((a, b) => b - a);

  return (
    <div className="space-y-3">
      {years.map((y) => (
        <div key={y} className="rounded-xl border bg-card overflow-hidden">
          <div className="px-4 py-2 bg-primary/10 border-b border-primary/20 flex items-center gap-2">
            <span className="text-lg font-bold text-primary tabular-nums">{y}</span>
            <span className="text-xs text-muted-foreground">
              {y === 2024 ? "Eleições Municipais" : y === 2022 ? "Eleições Gerais" : ""}
            </span>
          </div>
          <ul className="divide-y divide-border">
            {byYear.get(y)!.map((item) => {
              const w = item.winner;
              const ru = item.runner_up;
              const pct = w && item.total_votes > 0
                ? (w.votes / item.total_votes) * 100
                : 0;
              const roundLabel = (item.round ?? 1) === 2 ? " · 2º turno" : (item.round ?? 1) === 1 && hasMultiRounds(byYear.get(y)!, item.office_code) ? " · 1º turno" : "";
              return (
                <li key={`${y}-${item.office_code}-${item.round ?? 1}`} className="p-3 sm:p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <Crown className="w-4 h-4 text-primary shrink-0" />
                    <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
                      {item.office_name}<span className="text-primary normal-case">{roundLabel}</span>
                    </p>
                  </div>
                  {w ? (
                    <Link
                      href={`/dashboard/analises/candidato/${w.candidate_id}`}
                      className="flex items-center gap-3 hover:bg-accent/30 -mx-2 px-2 py-1.5 rounded-md transition-colors"
                    >
                      <PartyLogo number={w.party_number} abbreviation={w.party_abbr} size="sm" />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold truncate">
                          {w.urn_name}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          <span className="text-primary font-semibold">{w.party_abbr}</span>
                          {" · "}
                          <AnimatedNumber value={w.votes} /> votos
                          {pct > 0 && ` · ${pct.toFixed(1)}%`}
                        </p>
                      </div>
                      {w.result_status && (
                        <ResultBadge status={w.result_status} size="sm" />
                      )}
                    </Link>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">Sem dados.</p>
                  )}
                  {ru && (
                    <p className="text-xs text-muted-foreground mt-2 ml-7">
                      2º lugar: <span className="font-semibold">{ru.urn_name}</span>{" "}
                      ({ru.party_abbr}) · {new Intl.NumberFormat("pt-BR").format(ru.votes)} votos
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function Breakdown({
  title,
  data,
  total,
  palette,
}: {
  title: string;
  data: Record<string, number>;
  total: number;
  palette: string[];
}) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2.5">{title}</p>
      <ul className="space-y-2">
        {entries.map(([label, value], i) => {
          const pct = total > 0 ? (value / total) * 100 : 0;
          const color = palette[i % palette.length];
          return (
            <li key={label}>
              <div className="flex items-center justify-between text-xs mb-0.5">
                <span className="truncate flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: color }} />
                  {label}
                </span>
                <span className="text-muted-foreground font-mono shrink-0">
                  {pctFmt.format(pct)}%
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full transition-[width] duration-700 ease-out"
                  style={{ width: `${(value / max) * 100}%`, background: color }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// Paletas por categoria (tons coerentes com o tema)
const PAL_GENDER = ["#ec4899", "#0ea5e9", "#a1a1aa"]; // F rosa, M azul, NI cinza
const PAL_AGE = ["#fde68a", "#fbbf24", "#f59e0b", "#ea580c", "#c2410c", "#9a3412", "#7c2d12"];
const PAL_EDU = ["#a1a1aa", "#94a3b8", "#22d3ee", "#0ea5e9", "#6366f1", "#a855f7"];

function Stat({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: number | null;
  accent?: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border bg-card/60 p-4 text-center">
      {value === null ? (
        <div className="h-8 w-20 mx-auto rounded bg-muted animate-pulse" />
      ) : (
        <p className={`text-2xl font-bold ${accent ?? ""}`}>{numberFmt.format(value)}</p>
      )}
      <p className="text-xs text-muted-foreground mt-1">{label}</p>
      {hint && <p className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</p>}
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
