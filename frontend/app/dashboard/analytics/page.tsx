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
  TrendingUp,
  Users,
  Vote,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Page, TseCandidate, TseElection, TseParty } from "@/lib/types";

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

async function load(): Promise<Data> {
  const total = (p: string) =>
    api<{ total: number }>(p).then((r) => r.total).catch(() => 0);
  const [
    contacts,
    demandsOpen,
    candidates,
    parties,
    elections,
    prefeitos,
    vereadores,
  ] = await Promise.all([
    total("/v1/contacts?limit=1"),
    total("/v1/demands?status=aberta&limit=1"),
    total("/v1/tse/candidates?limit=1"),
    api<TseParty[]>("/v1/tse/parties").then((r) => r.length).catch(() => 0),
    api<TseElection[]>("/v1/tse/elections").then((r) => r.length).catch(() => 0),
    total("/v1/tse/candidates?office_code=11&limit=1"),
    total("/v1/tse/candidates?office_code=13&limit=1"),
  ]);
  return {
    contacts,
    demandsOpen,
    candidates,
    parties,
    elections,
    prefeitos,
    vereadores,
  };
}

export default function PainelPage() {
  const [d, setD] = useState<Data | null>(null);

  useEffect(() => {
    load().then(setD);
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
