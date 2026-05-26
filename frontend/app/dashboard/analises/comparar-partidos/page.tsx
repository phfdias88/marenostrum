"use client";

/**
 * Comparar partidos lado a lado — /dashboard/analises/comparar-partidos.
 * - escolhe ano + cargo, e até 4 partidos (chips)
 * - usa /stats/party-performance (1 chamada traz todos) e filtra os escolhidos
 * - cards com eleitos/votos/candidatos, líder destacado
 * - URL compartilhável: ?ids=13,15,22&year=2024&office=11
 * - Exportar PNG
 */
import { ArrowLeft, Plus, Trophy, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { TseParty, TsePartyPerformanceResponse, TsePartyPerformanceItem } from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { ExportShare } from "@/components/tse/ExportShare";

const MAX = 4;
const numberFmt = new Intl.NumberFormat("pt-BR");

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
  ],
};

export default function CompararPartidosPage() {
  const [year, setYear] = useState("2024");
  const [office, setOffice] = useState("11");
  const [state, setState] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [hydrating, setHydrating] = useState(true);

  const [parties, setParties] = useState<TseParty[]>([]);
  const [perf, setPerf] = useState<TsePartyPerformanceResponse | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  // Hidrata da URL ?ids=&year=&office=
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const ids = sp.get("ids")?.split(",").map(Number).filter((n) => !Number.isNaN(n)).slice(0, MAX);
    if (sp.get("year")) setYear(sp.get("year")!);
    if (sp.get("office")) setOffice(sp.get("office")!);
    if (ids && ids.length) setSelected(ids);
    setHydrating(false);
  }, []);

  // Sincroniza URL
  useEffect(() => {
    if (hydrating) return;
    const url = new URL(window.location.href);
    if (selected.length) url.searchParams.set("ids", selected.join(","));
    else url.searchParams.delete("ids");
    url.searchParams.set("year", year);
    url.searchParams.set("office", office);
    window.history.replaceState(null, "", url.toString());
  }, [selected, year, office, hydrating]);

  useEffect(() => {
    api<TseParty[]>("/v1/tse/parties").then(setParties).catch(() => setParties([]));
  }, []);

  useEffect(() => {
    setPerf(null);
    const p = new URLSearchParams({ year, office_code: office });
    if (state) p.set("state", state);
    api<TsePartyPerformanceResponse>(`/v1/tse/stats/party-performance?${p.toString()}`)
      .then(setPerf)
      .catch(() => setPerf(null));
  }, [year, office, state]);

  const perfByNumber = useMemo(() => {
    const m = new Map<number, TsePartyPerformanceItem>();
    (perf?.items ?? []).forEach((i) => m.set(i.party.number, i));
    return m;
  }, [perf]);

  const partyByNumber = useMemo(() => {
    const m = new Map<number, TseParty>();
    parties.forEach((p) => m.set(p.number, p));
    return m;
  }, [parties]);

  const maxElected = Math.max(
    1,
    ...selected.map((n) => perfByNumber.get(n)?.elected_count ?? 0),
  );

  function toggle(n: number) {
    setSelected((cur) =>
      cur.includes(n) ? cur.filter((x) => x !== n) : [...cur, n].slice(0, MAX),
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/dashboard/analises"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Análises
        </Link>
        {selected.length >= 2 && (
          <div data-html2canvas-ignore>
            <ExportShare targetRef={cardRef} filename="comparar-partidos" />
          </div>
        )}
      </div>

      <header className="mb-5">
        <h1 className="text-2xl font-bold">Comparar partidos</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Até {MAX} partidos lado a lado — eleitos, votos e candidatos por cargo.
        </p>
      </header>

      {/* Filtros */}
      <section className="grid grid-cols-2 md:grid-cols-12 gap-3 mb-4">
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
          className="md:col-span-4"
        />
        <Select
          label="Cargo"
          value={office}
          onChange={setOffice}
          options={OFFICES_BY_YEAR[year]}
          className="md:col-span-5"
        />
        <Select
          label="UF"
          value={state}
          onChange={setState}
          options={[{ value: "", label: "Brasil" }, ...TSE_STATES.map((s) => ({ value: s, label: s }))]}
          className="md:col-span-3"
        />
      </section>

      {/* Seletor de partidos (chips) */}
      <section className="mb-6">
        <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
          Escolha os partidos ({selected.length}/{MAX})
        </p>
        <div className="flex flex-wrap gap-2">
          {parties
            .slice()
            .sort((a, b) => a.number - b.number)
            .map((p) => {
              const on = selected.includes(p.number);
              const disabled = !on && selected.length >= MAX;
              return (
                <button
                  key={p.id}
                  onClick={() => toggle(p.number)}
                  disabled={disabled}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border text-sm transition-colors ${
                    on
                      ? "border-primary bg-primary/15 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground hover:border-primary/50 disabled:opacity-40"
                  }`}
                >
                  <PartyLogo number={p.number} abbreviation={p.abbreviation} size="sm" />
                  {p.abbreviation}
                  {on && <X className="w-3 h-3" />}
                </button>
              );
            })}
        </div>
      </section>

      {/* Cards comparativos */}
      {selected.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
          <Plus className="mx-auto h-9 w-9 text-muted-foreground" />
          <p className="mt-3 font-semibold">Escolha pelo menos 2 partidos acima</p>
          <p className="text-sm text-muted-foreground mt-1">
            Os números aparecem lado a lado pro cargo/ano selecionado.
          </p>
        </div>
      ) : (
        <div
          ref={cardRef}
          className="grid gap-4"
          style={{ gridTemplateColumns: `repeat(${selected.length}, minmax(0, 1fr))` }}
        >
          {selected.map((n) => {
            const party = partyByNumber.get(n);
            const item = perfByNumber.get(n);
            const elected = item?.elected_count ?? 0;
            const isLeader = selected.length > 1 && elected === maxElected && elected > 0;
            return (
              <div
                key={n}
                className={`rounded-xl border bg-card p-4 relative ${
                  isLeader ? "border-primary ring-1 ring-primary/40" : "border-border"
                }`}
              >
                {isLeader && (
                  <span className="absolute -top-2 left-1/2 -translate-x-1/2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold">
                    <Trophy className="w-3 h-3" /> MAIS ELEITOS
                  </span>
                )}
                <button
                  data-html2canvas-ignore
                  onClick={() => toggle(n)}
                  className="absolute top-2 right-2 text-muted-foreground hover:text-foreground p-1"
                >
                  <X className="w-4 h-4" />
                </button>
                <div className="flex flex-col items-center text-center pt-2">
                  <PartyLogo number={n} abbreviation={party?.abbreviation ?? String(n)} size="lg" />
                  <Link
                    href={`/dashboard/analises/partido/${n}`}
                    className="font-bold mt-2 hover:underline"
                  >
                    {party?.abbreviation ?? n}
                  </Link>
                  <p className="text-xs text-muted-foreground truncate w-full">{party?.name ?? ""}</p>
                </div>
                <hr className="my-3 border-border" />
                <div className="space-y-3">
                  <div>
                    <p className="text-xs uppercase tracking-wider text-muted-foreground">Eleitos</p>
                    <p className="text-2xl font-bold text-primary">{numberFmt.format(elected)}</p>
                    <div className="mt-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-primary transition-all"
                        style={{ width: `${(elected / maxElected) * 100}%` }}
                      />
                    </div>
                  </div>
                  <Metric label="Votos nominais" value={item?.total_votes ?? 0} />
                  <Metric label="Candidatos" value={item?.candidates_count ?? 0} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm border-t border-border/40 pt-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono font-semibold">{numberFmt.format(value)}</span>
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
