"use client";

/**
 * Painel — visão consolidada CRM + dados públicos TSE.
 * (Substitui o antigo embed externo "Insights" que nunca foi configurado.)
 */
import {
  ArrowRight,
  Building2,
  ClipboardList,
  FileBarChart,
  Landmark,
  MapPin,
  Sparkles,
  TrendingUp,
  Users,
  Vote,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { TsePartyPerformanceResponse } from "@/lib/types";

const numberFmt = new Intl.NumberFormat("pt-BR");

type Data = {
  contacts: number;
  demandsOpen: number;
  candidates: number;
  parties: number;
  elections: number;
  prefeitos: number;
  vereadores: number;
};

type Counts = {
  candidates: number;
  by_office: Record<string, number>;
  municipalities: number;
  parties: number;
  elections: number;
};

async function load(): Promise<Data> {
  const total = (p: string) =>
    api<{ total: number }>(p).then((r) => r.total).catch(() => 0);
  // Contagens EXATAS do TSE 2024 (não o total capado em 5000 de /candidates)
  const counts = api<Counts>("/v1/tse/stats/counts?year=2024").catch(
    (): Counts => ({ candidates: 0, by_office: {}, municipalities: 0, parties: 0, elections: 0 }),
  );
  const [contacts, demandsOpen, c] = await Promise.all([
    total("/v1/contacts?limit=1"),
    total("/v1/demands?status=aberta&limit=1"),
    counts,
  ]);
  return {
    contacts,
    demandsOpen,
    candidates: c.candidates,
    parties: c.parties,
    elections: c.elections,
    prefeitos: c.by_office["11"] ?? 0,
    vereadores: c.by_office["13"] ?? 0,
  };
}

export default function PainelPage() {
  const [d, setD] = useState<Data | null>(null);

  const [perf, setPerf] = useState<TsePartyPerformanceResponse | null>(null);

  useEffect(() => {
    load().then(setD);
    api<TsePartyPerformanceResponse>(
      "/v1/tse/stats/party-performance?year=2024&office_code=11",
    )
      .then(setPerf)
      .catch(() => setPerf(null));
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-6 py-10 space-y-10">
      <header>
        <p className="text-sm font-medium text-primary flex items-center gap-1.5">
          <TrendingUp className="w-4 h-4" /> Painel
        </p>
        <h1 className="text-3xl font-bold tracking-tight mt-1">
          Visão consolidada
        </h1>
        <p className="text-muted-foreground mt-1">
          Sua campanha (CRM) + a base eleitoral pública do TSE, num só lugar.
        </p>
      </header>

      {/* Base TSE */}
      <section>
        <SectionTitle icon={Landmark} title="Base eleitoral (TSE 2024)" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <BigStat
            label="Candidatos"
            value={d?.candidates}
            icon={Users}
            gradient="from-blue-600/20 to-blue-500/5"
            accent="text-blue-400"
          />
          <BigStat
            label="Municípios"
            value={5568}
            icon={MapPin}
            gradient="from-emerald-600/20 to-emerald-500/5"
            accent="text-emerald-400"
            ready
          />
          <BigStat
            label="Partidos"
            value={d?.parties}
            icon={Building2}
            gradient="from-fuchsia-600/20 to-fuchsia-500/5"
            accent="text-fuchsia-400"
          />
          <BigStat
            label="Eleições"
            value={d?.elections}
            icon={FileBarChart}
            gradient="from-amber-600/20 to-amber-500/5"
            accent="text-amber-400"
          />
        </div>

        {/* Breakdown cargo */}
        {d && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            <CargoBar
              label="Prefeitos"
              value={d.prefeitos}
              total={d.prefeitos + d.vereadores}
              color="bg-blue-500"
            />
            <CargoBar
              label="Vereadores"
              value={d.vereadores}
              total={d.prefeitos + d.vereadores}
              color="bg-emerald-500"
            />
          </div>
        )}
      </section>

      {/* Insights automáticos */}
      <section>
        <SectionTitle icon={Sparkles} title="Destaques automáticos" />
        <InsightsPanel perf={perf} data={d} />
      </section>

      {/* Gráfico: prefeitos eleitos por partido 2024 */}
      <section>
        <SectionTitle icon={Landmark} title="Prefeituras conquistadas por partido (2024)" />
        <PartyBarChart data={perf} />
        <div className="mt-2 text-right">
          <Link href="/dashboard/analises/partidos" className="text-sm text-primary hover:underline">
            Ver análise completa por partido →
          </Link>
        </div>
      </section>

      {/* Votos nominais por partido + concentração */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <SectionTitle icon={Vote} title="Votos nominais por partido — prefeito (2024)" />
          <PartyVotesChart data={perf} />
        </div>
        <div>
          <SectionTitle icon={Landmark} title="Concentração" />
          <ConcentrationDonut data={perf} />
        </div>
      </section>

      {/* CRM */}
      <section>
        <SectionTitle icon={Users} title="Sua campanha (CRM)" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <BigStat
            label="Contatos"
            value={d?.contacts}
            icon={Users}
            gradient="from-primary/20 to-primary/5"
            accent="text-primary"
          />
          <BigStat
            label="Demandas abertas"
            value={d?.demandsOpen}
            icon={ClipboardList}
            gradient="from-amber-600/20 to-amber-500/5"
            accent="text-amber-400"
          />
        </div>
      </section>

      {/* Atalhos pra análise */}
      <section>
        <SectionTitle icon={Vote} title="Explorar análises" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <ExploreCard
            title="Análise de Eleição"
            desc="Ranking por cidade e cargo: votos, % e quem foi eleito."
            href="/dashboard/analises/eleicao"
            icon={Vote}
          />
          <ExploreCard
            title="Candidatos"
            desc="Busque qualquer candidato e veja votos por município."
            href="/dashboard/analises/candidato"
            icon={Users}
          />
          <ExploreCard
            title="Bairros"
            desc="Votos de um candidato bairro a bairro, no mapa."
            href="/dashboard/analises/bairros"
            icon={MapPin}
          />
        </div>
      </section>
    </div>
  );
}

// ----------------------------------------------------------------- pieces

/**
 * Gera frases de destaque a partir dos dados já carregados (sem backend novo).
 * Tudo derivado de party-performance 2024 (prefeitos) + contagens da base.
 */
function buildInsights(
  perf: TsePartyPerformanceResponse | null,
  data: Data | null,
): string[] {
  const out: string[] = [];
  if (perf && perf.items.length > 0) {
    const ranked = perf.items
      .filter((i) => i.elected_count > 0)
      .sort((a, b) => b.elected_count - a.elected_count);
    const totalElected = perf.total_elected || ranked.reduce((s, i) => s + i.elected_count, 0);

    if (ranked[0] && totalElected > 0) {
      const pct = ((ranked[0].elected_count / totalElected) * 100).toFixed(1);
      out.push(
        `${ranked[0].party.abbreviation} foi o partido que mais elegeu prefeitos em 2024: ${numberFmt.format(ranked[0].elected_count)} (${pct}% do total nacional).`,
      );
    }
    if (ranked.length >= 3) {
      const top3 = ranked.slice(0, 3).reduce((s, i) => s + i.elected_count, 0);
      const pct3 = ((top3 / totalElected) * 100).toFixed(1);
      out.push(
        `Os 3 maiores partidos (${ranked.slice(0, 3).map((i) => i.party.abbreviation).join(", ")}) concentram ${pct3}% das prefeituras.`,
      );
    }
    out.push(
      `${numberFmt.format(ranked.length)} partidos elegeram ao menos um prefeito no país.`,
    );
    if (ranked.length > 0) {
      const avg = Math.round(totalElected / ranked.length);
      out.push(
        `Em média, cada partido vitorioso conquistou ${numberFmt.format(avg)} prefeituras.`,
      );
    }
  }
  if (data) {
    if (data.candidates > 0 && data.parties > 0) {
      out.push(
        `A base reúne ${numberFmt.format(data.candidates)} candidatos distribuídos em ${numberFmt.format(data.parties)} partidos.`,
      );
    }
    if (data.vereadores > 0 && data.prefeitos > 0) {
      const ratio = (data.vereadores / data.prefeitos).toFixed(1);
      out.push(
        `Há ${ratio} candidatos a vereador para cada candidato a prefeito.`,
      );
    }
  }
  return out;
}

function InsightsPanel({
  perf,
  data,
}: {
  perf: TsePartyPerformanceResponse | null;
  data: Data | null;
}) {
  const insights = buildInsights(perf, data);
  if (!perf || !data) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 rounded-xl border border-border bg-card/40 animate-pulse" />
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {insights.map((text, i) => (
        <div
          key={i}
          className="rounded-xl border border-border bg-card p-4 flex items-start gap-3"
        >
          <span className="grid place-items-center w-8 h-8 rounded-lg bg-primary/15 text-primary shrink-0 mt-0.5">
            <Sparkles className="w-4 h-4" />
          </span>
          <p className="text-sm leading-relaxed">{text}</p>
        </div>
      ))}
    </div>
  );
}

const numberFmtCompact = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Top 10 partidos por votos nominais (complementa o gráfico de eleitos). */
function PartyVotesChart({ data }: { data: TsePartyPerformanceResponse | null }) {
  if (!data) {
    return <div className="h-48 rounded-xl border border-border bg-card/40 animate-pulse" />;
  }
  const top = [...data.items]
    .filter((i) => i.total_votes > 0)
    .sort((a, b) => b.total_votes - a.total_votes)
    .slice(0, 10);
  const max = Math.max(1, ...top.map((i) => i.total_votes));
  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-2.5">
      {top.map((i) => (
        <div key={i.party.id} className="flex items-center gap-3">
          <span className="w-16 shrink-0 text-sm font-bold text-right">
            {i.party.abbreviation}
          </span>
          <div className="flex-1 h-6 rounded-md bg-muted overflow-hidden relative">
            <div
              className="h-full bg-gradient-to-r from-sky-500 to-cyan-400 flex items-center justify-end pr-2"
              style={{ width: `${(i.total_votes / max) * 100}%` }}
            >
              <span className="text-xs font-bold text-background">
                {numberFmtCompact.format(i.total_votes)}
              </span>
            </div>
          </div>
        </div>
      ))}
      <p className="text-xs text-muted-foreground pt-1">
        {numberFmt.format(data.total_votes)} votos nominais no total · top 10 partidos
      </p>
    </div>
  );
}

/** Donut: fatia de prefeituras dos top 5 partidos vs resto. */
function ConcentrationDonut({ data }: { data: TsePartyPerformanceResponse | null }) {
  if (!data) {
    return <div className="h-48 rounded-xl border border-border bg-card/40 animate-pulse" />;
  }
  const total = data.total_elected || 1;
  const ranked = [...data.items]
    .filter((i) => i.elected_count > 0)
    .sort((a, b) => b.elected_count - a.elected_count);
  const top5 = ranked.slice(0, 5);
  const colors = ["#eab308", "#0ea5e9", "#22c55e", "#a855f7", "#f97316"];
  const restCount = total - top5.reduce((s, i) => s + i.elected_count, 0);

  const slices = [
    ...top5.map((i, idx) => ({
      label: i.party.abbreviation,
      value: i.elected_count,
      color: colors[idx],
    })),
    { label: "Outros", value: Math.max(0, restCount), color: "#3f3f46" },
  ];

  // conic-gradient stops
  let acc = 0;
  const stops = slices
    .map((s) => {
      const start = (acc / total) * 360;
      acc += s.value;
      const end = (acc / total) * 360;
      return `${s.color} ${start}deg ${end}deg`;
    })
    .join(", ");

  return (
    <div className="rounded-xl border border-border bg-card p-5 flex flex-col items-center">
      <div
        className="w-36 h-36 rounded-full"
        style={{ background: `conic-gradient(${stops})` }}
      >
        <div className="w-full h-full rounded-full grid place-items-center">
          <div className="w-20 h-20 rounded-full bg-card grid place-items-center text-center">
            <div>
              <p className="text-lg font-bold leading-none">{numberFmt.format(total)}</p>
              <p className="text-[10px] text-muted-foreground">prefeituras</p>
            </div>
          </div>
        </div>
      </div>
      <ul className="mt-4 w-full space-y-1.5">
        {slices.map((s) => (
          <li key={s.label} className="flex items-center gap-2 text-xs">
            <span className="w-3 h-3 rounded-sm shrink-0" style={{ background: s.color }} />
            <span className="flex-1 truncate">{s.label}</span>
            <span className="font-mono text-muted-foreground">
              {((s.value / total) * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PartyBarChart({ data }: { data: TsePartyPerformanceResponse | null }) {
  if (!data) {
    return <div className="h-48 rounded-xl border border-border bg-card/40 animate-pulse" />;
  }
  const top = data.items.filter((i) => i.elected_count > 0).slice(0, 10);
  const max = Math.max(1, ...top.map((i) => i.elected_count));
  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-2.5">
      {top.map((i) => (
        <div key={i.party.id} className="flex items-center gap-3">
          <span className="w-16 shrink-0 text-sm font-bold text-right">
            {i.party.abbreviation}
          </span>
          <div className="flex-1 h-6 rounded-md bg-muted overflow-hidden relative">
            <div
              className="h-full bg-gradient-to-r from-primary to-amber-500 flex items-center justify-end pr-2"
              style={{ width: `${(i.elected_count / max) * 100}%` }}
            >
              <span className="text-xs font-bold text-primary-foreground">
                {numberFmt.format(i.elected_count)}
              </span>
            </div>
          </div>
        </div>
      ))}
      <p className="text-xs text-muted-foreground pt-1">
        {numberFmt.format(data.total_elected)} prefeitos eleitos no Brasil · top 10 partidos
      </p>
    </div>
  );
}

function SectionTitle({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-5 h-5 text-muted-foreground" />
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
    </div>
  );
}

function BigStat({
  label,
  value,
  icon: Icon,
  gradient,
  accent,
  ready,
}: {
  label: string;
  value: number | undefined;
  icon: LucideIcon;
  gradient: string;
  accent: string;
  ready?: boolean;
}) {
  const show = ready || value !== undefined;
  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-border bg-gradient-to-br ${gradient} p-5`}
    >
      <Icon className={`absolute right-3 top-3 w-8 h-8 opacity-20 ${accent}`} />
      <p className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      {show ? (
        <p className={`text-3xl font-bold mt-2 ${accent}`}>
          {numberFmt.format(value ?? 0)}
        </p>
      ) : (
        <div className="h-9 w-20 bg-muted/50 rounded animate-pulse mt-2" />
      )}
    </div>
  );
}

function CargoBar({
  label,
  value,
  total,
  color,
}: {
  label: string;
  value: number;
  total: number;
  color: string;
}) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium">{label}</span>
        <span className="font-mono font-bold">{numberFmt.format(value)}</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function ExploreCard({
  title,
  desc,
  href,
  icon: Icon,
}: {
  title: string;
  desc: string;
  href: string;
  icon: LucideIcon;
}) {
  return (
    <Link
      href={href}
      className="group rounded-xl border border-border bg-card p-5 hover:border-primary/60 hover:bg-card/80 transition-all hover:-translate-y-0.5"
    >
      <div className="flex items-center gap-3">
        <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary group-hover:bg-primary/25">
          <Icon className="w-5 h-5" />
        </span>
        <h3 className="font-semibold">{title}</h3>
      </div>
      <p className="text-sm text-muted-foreground mt-3">{desc}</p>
      <span className="inline-flex items-center gap-1 text-sm text-primary mt-3 group-hover:gap-2 transition-all">
        Abrir <ArrowRight className="w-4 h-4" />
      </span>
    </Link>
  );
}
