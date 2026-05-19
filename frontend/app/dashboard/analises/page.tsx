"use client";

/**
 * Hub de Analises (estilo Politique).
 *
 * Cartoes:
 *  - Candidatos:  /analises/candidato     (implementado)
 *  - Partidos:    /analises/partidos      (implementado)
 *  - Municipios:  /analises/municipios    (em breve)
 *  - Eleicoes:    /analises/eleicoes      (em breve)
 *  - Comparar:    /analises/comparar      (em breve)
 *  - Bairros:     /dashboard/map          (reusa heatmap)
 *  - Zona:        /analises/zona          (em breve — depende de dataset por zona)
 *  - Sincronizar: dispara /tse/sync       (modal)
 *
 * Mostra ainda o status do dataset TSE: quantos candidatos/municipios/etc
 * estao importados — se zero, sugere disparar sync.
 */
import {
  Building2,
  Compass,
  FileBarChart,
  Loader2,
  MapPin,
  Map as MapIcon,
  RefreshCw,
  ScanSearch,
  Users,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { Page, TseCandidate, TseElection, TseParty, TseSyncJob } from "@/lib/types";
import { Button } from "@/components/ui/button";

// ------------------------------------------------------------------- stats

type Stats = {
  parties: number;
  elections: number;
  candidates: number;
  lastSync: TseSyncJob | null;
};

async function loadStats(): Promise<Stats> {
  const [parties, elections, page, jobs] = await Promise.all([
    api<TseParty[]>("/v1/tse/parties").catch(() => []),
    api<TseElection[]>("/v1/tse/elections").catch(() => []),
    api<Page<TseCandidate>>("/v1/tse/candidates?limit=1").catch(
      () => ({ items: [], total: 0, limit: 1, offset: 0 }) as Page<TseCandidate>,
    ),
    api<TseSyncJob[]>("/v1/tse/sync").catch(() => []),
  ]);
  return {
    parties: parties.length,
    elections: elections.length,
    candidates: page.total,
    lastSync: jobs[0] ?? null,
  };
}

// ------------------------------------------------------------------- cards

type Card = {
  href: string;
  label: string;
  icon: LucideIcon;
  description: string;
  disabled?: boolean;
};

const CARDS: Card[] = [
  {
    href: "/dashboard/analises/candidato",
    label: "Candidatos",
    icon: Users,
    description: "Busque por UF, cargo, partido, nome. Veja votos por município.",
  },
  {
    href: "/dashboard/analises/partidos",
    label: "Partidos",
    icon: Building2,
    description: "Os 29 partidos brasileiros, com seus candidatos por estado.",
  },
  {
    href: "/dashboard/analises/municipios",
    label: "Municípios",
    icon: MapPin,
    description: "Top candidatos por município — 5.568 cidades importadas.",
  },
  {
    href: "/dashboard/analises/eleicoes",
    label: "Eleições",
    icon: FileBarChart,
    description: "Eleições municipais 2024 (ordinárias e suplementares).",
  },
  {
    href: "/dashboard/analises/comparar",
    label: "Comparar",
    icon: UsersRound,
    description: "Coloque candidatos lado a lado e compare cenários.",
  },
  {
    href: "/dashboard/map",
    label: "Bairros (heatmap)",
    icon: MapIcon,
    description: "Use o mapa de votos próprios (locais de votação do tenant).",
  },
  {
    href: "/dashboard/analises/zona",
    label: "Zona eleitoral",
    icon: Compass,
    description: "Análise por zona — em breve (depende de dataset por zona).",
    disabled: true,
  },
];

// ------------------------------------------------------------------- page

export default function AnalisesHubPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    loadStats().then((s) => {
      setStats(s);
      setLoading(false);
    });
  }, []);

  async function triggerSync() {
    setSyncing(true);
    try {
      const res = await api<TseSyncJob>(
        "/v1/tse/sync?dataset=candidato_munzona_2024",
        { method: "POST" },
      );
      toast.success(
        `Sincronização iniciada (job ${res.id.slice(0, 8)}…) — leva ~10min.`,
      );
      // refresh stats periodicamente
      const refresh = async () => {
        const fresh = await loadStats();
        setStats(fresh);
        if (
          fresh.lastSync &&
          (fresh.lastSync.status === "running" ||
            fresh.lastSync.status === "pending")
        ) {
          setTimeout(refresh, 5000);
        } else {
          setSyncing(false);
        }
      };
      setTimeout(refresh, 3000);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Falha ao sincronizar.";
      toast.error(msg);
      setSyncing(false);
    }
  }

  const hasData = (stats?.candidates ?? 0) > 0;
  const job = stats?.lastSync;

  return (
    <div className="max-w-7xl mx-auto px-6 py-10 space-y-10">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-wider text-muted-foreground">
            Inteligência eleitoral
          </p>
          <h1 className="text-3xl font-bold mt-1">Análises (TSE)</h1>
          <p className="text-muted-foreground mt-1 max-w-xl">
            Dados públicos oficiais do Tribunal Superior Eleitoral — Brasil
            inteiro, 2024.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {job && <SyncBadge job={job} />}
          <Button onClick={triggerSync} disabled={syncing} variant="outline">
            {syncing ? (
              <Loader2 className="animate-spin" />
            ) : (
              <RefreshCw />
            )}
            Sincronizar TSE
          </Button>
        </div>
      </header>

      {/* Stats banner */}
      {loading ? (
        <div className="h-24 rounded-lg bg-card/60 border border-border animate-pulse" />
      ) : (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Candidatos" value={stats?.candidates ?? 0} />
          <Stat label="Municípios" value={5568} hint="todos do Brasil" />
          <Stat label="Partidos" value={stats?.parties ?? 0} />
          <Stat label="Eleições" value={stats?.elections ?? 0} />
        </section>
      )}

      {/* Empty state quando sem dados */}
      {!loading && !hasData && (
        <div className="rounded-xl border border-dashed border-border p-8 text-center bg-card/40">
          <ScanSearch className="mx-auto h-12 w-12 text-muted-foreground" />
          <p className="text-lg font-semibold mt-3">Nenhum dado TSE ainda</p>
          <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
            Clique em <span className="font-medium">Sincronizar TSE</span> pra
            baixar o dataset oficial de candidatos & votação por município.
            Demora ~10min.
          </p>
        </div>
      )}

      {/* Cards */}
      <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {CARDS.map((c) => {
          const Icon = c.icon;
          const blocked = c.disabled || (!hasData && c.href.includes("/analises/"));
          const body = (
            <div
              className={`group h-full rounded-xl border bg-card p-5 transition-all
                          ${
                            blocked
                              ? "border-border/60 opacity-60 cursor-not-allowed"
                              : "border-border hover:border-primary/60 hover:bg-card/80 hover:-translate-y-0.5"
                          }`}
            >
              <div className="flex items-center gap-3">
                <span
                  className={`grid place-items-center w-11 h-11 rounded-lg
                              ${
                                blocked
                                  ? "bg-muted text-muted-foreground"
                                  : "bg-primary/15 text-primary group-hover:bg-primary/25"
                              }`}
                >
                  <Icon className="w-5 h-5" />
                </span>
                <h3 className="font-semibold text-base">{c.label}</h3>
              </div>
              <p className="text-sm text-muted-foreground mt-3 leading-relaxed">
                {c.description}
              </p>
              {c.disabled && (
                <p className="mt-3 text-xs uppercase tracking-wide text-amber-500">
                  Em breve
                </p>
              )}
            </div>
          );
          return blocked ? (
            <div key={c.href}>{body}</div>
          ) : (
            <Link key={c.href} href={c.href} className="block h-full">
              {body}
            </Link>
          );
        })}
      </section>

      <footer className="text-xs text-muted-foreground text-center pt-4">
        Fonte: Tribunal Superior Eleitoral · dadosabertos.tse.jus.br
      </footer>
    </div>
  );
}

// ------------------------------------------------------------------- subs

const numberFmt = new Intl.NumberFormat("pt-BR");

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border bg-card/60 px-4 py-3">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="text-2xl font-bold mt-1">{numberFmt.format(value)}</p>
      {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
    </div>
  );
}

function SyncBadge({ job }: { job: TseSyncJob }) {
  const tone =
    job.status === "completed"
      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
      : job.status === "running" || job.status === "pending"
        ? "bg-blue-500/15 text-blue-400 border-blue-500/30 animate-pulse"
        : "bg-red-500/15 text-red-400 border-red-500/30";
  const label =
    job.status === "running"
      ? `sincronizando… ${numberFmt.format(job.rows_processed)} linhas`
      : job.status === "completed"
        ? `última sync OK · ${numberFmt.format(job.candidates_imported)} candidatos`
        : job.status === "failed"
          ? "última sync falhou"
          : "sync pendente";
  return (
    <span
      className={`text-xs px-2.5 py-1 rounded-full border ${tone} font-medium`}
    >
      {label}
    </span>
  );
}
