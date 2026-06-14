"use client";

/**
 * Dashboard: visao geral pos-login.
 *
 * KPIs vem de queries leves nos endpoints existentes (limit=1 retorna total).
 * Evita criar endpoint /stats novo — reusa o que ja temos.
 */
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Circle,
  ClipboardList,
  Clock,
  Loader2,
  MapPinned,
  Plus,
  Rocket,
  TrendingUp,
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { clearAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { InsightCarousel } from "@/components/tse/InsightCarousel";
import { PullToRefresh } from "@/components/ui/PullToRefresh";
import { BirthdaysCard } from "@/components/contacts/BirthdaysCard";

// -------------------------------------------------------------------- types

type Me = {
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  tenant_id: string;
  tenant_slug: string;
  tenant_name: string;
};

type Stats = {
  contacts: number;
  demandsOpen: number;
  demandsInProgress: number;
  demandsResolved: number;
  contactsOnMap: number;
};

// ---------------------------------------------------------------- formatter

const numberFmt = new Intl.NumberFormat("pt-BR");

function roleLabel(role: string): string {
  return (
    { owner: "Candidato / Owner", manager: "Coordenador", staff: "Equipe", volunteer: "Voluntário" }[
      role
    ] ?? role
  );
}

// ---------------------------------------------------------------- page

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(force = false) {
    // force=true (pull-to-refresh): ignora o cache em memória e vai à rede.
    const o = force ? { skipCache: true } : {};
    const total = (path: string) =>
      api<{ total: number }>(path, o).then((r) => r.total).catch(() => 0);
    try {
      const [m, c, dOpen, dProg, dRes, mapC] = await Promise.all([
        api<Me>("/v1/auth/me", o),
        total("/v1/contacts?limit=1"),
        total("/v1/demands?status=aberta&limit=1"),
        total("/v1/demands?status=em_andamento&limit=1"),
        total("/v1/demands?status=resolvida&limit=1"),
        api<unknown[]>("/v1/contacts/map", o).then((r) => r.length).catch(() => 0),
      ]);
      setMe(m);
      setStats({
        contacts: c,
        demandsOpen: dOpen,
        demandsInProgress: dProg,
        demandsResolved: dRes,
        contactsOnMap: mapC,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearAuth();
        router.replace("/login");
        return;
      }
      setError(err instanceof ApiError ? err.message : "Erro ao carregar.");
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  if (error) {
    return (
      <section className="max-w-7xl mx-auto px-6 py-10">
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-destructive">
          {error}
        </div>
      </section>
    );
  }

  return (
    <PullToRefresh onRefresh={() => load(true)}>
    <section className="max-w-7xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6 sm:space-y-8">
      {/* Hero header */}
      <header className="space-y-1">
        {me ? (
          <>
            <p className="text-sm font-medium text-primary">
              {me.tenant_name}
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">
              Olá, {me.full_name.split(" ")[0]} 👋
            </h1>
            <p className="text-muted-foreground">
              Visão geral da sua campanha em tempo real.
            </p>
          </>
        ) : (
          <div className="space-y-2">
            <div className="h-4 w-32 bg-muted rounded animate-pulse" />
            <div className="h-8 w-64 bg-muted rounded animate-pulse" />
          </div>
        )}
      </header>

      {/* Hero rotativo — insights TSE */}
      <InsightCarousel />

      {/* KPI cards — 2 colunas no mobile (cabe melhor sem scroll) */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <KpiCard
          label="Contatos no CRM"
          value={stats?.contacts}
          icon={Users}
          tone="brand"
          hint={
            stats && stats.contactsOnMap > 0
              ? `${numberFmt.format(stats.contactsOnMap)} com geolocalização`
              : "Cadastre seu primeiro contato"
          }
          href="/dashboard/contacts"
        />
        <KpiCard
          label="Demandas abertas"
          value={stats?.demandsOpen}
          icon={ClipboardList}
          tone="amber"
          hint="Aguardando primeira ação"
          href="/dashboard/demandas"
        />
        <KpiCard
          label="Em andamento"
          value={stats?.demandsInProgress}
          icon={Clock}
          tone="blue"
          hint="Sendo trabalhadas pela equipe"
          href="/dashboard/demandas"
        />
        <KpiCard
          label="Resolvidas"
          value={stats?.demandsResolved}
          icon={CheckCircle2}
          tone="emerald"
          hint="Histórico do mandato"
          href="/dashboard/demandas"
        />
      </div>

      {/* Primeiros passos — só aparece enquanto o CRM está começando
          (sem contatos OU sem demandas). Explica os zeros dos cards e
          converte melhor que um painel vazio. */}
      {stats && (stats.contacts === 0 ||
        stats.demandsOpen + stats.demandsInProgress + stats.demandsResolved === 0) && (
        <section className="rounded-2xl border border-primary/25 bg-gradient-to-br from-primary/[0.08] to-transparent p-5 sm:p-6">
          <div className="flex items-center gap-3 mb-4">
            <span className="grid place-items-center w-10 h-10 rounded-xl bg-primary/15 text-primary">
              <Rocket className="w-5 h-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Primeiros passos</h2>
              <p className="text-sm text-muted-foreground">
                Em 3 passos sua campanha está rodando no MareNostrum.
              </p>
            </div>
          </div>
          <ol className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <OnboardingStep
              n={1}
              done={stats.contacts > 0}
              title="Traga seus contatos"
              description="Importe a planilha de apoiadores (CSV) ou cadastre o primeiro eleitor."
              href="/dashboard/contacts"
              icon={Users}
            />
            <OnboardingStep
              n={2}
              done={stats.demandsOpen + stats.demandsInProgress + stats.demandsResolved > 0}
              title="Registre uma demanda"
              description="Pedidos de eleitores viram demandas com prazo, status e responsável."
              href="/dashboard/demandas"
              icon={ClipboardList}
            />
            <OnboardingStep
              n={3}
              done={false}
              title="Explore as análises"
              description="Votação por bairro, comparações e projeções com dados oficiais do TSE."
              href="/dashboard/analises"
              icon={BarChart3}
            />
          </ol>
        </section>
      )}

      {/* Ações rápidas */}
      <section>
        <div className="flex items-end justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Ações rápidas</h2>
            <p className="text-sm text-muted-foreground">
              Atalhos para as tarefas mais comuns.
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <QuickAction
            title="Novo contato"
            description="Cadastre um eleitor, liderança ou apoiador no CRM."
            icon={Plus}
            href="/dashboard/contacts"
          />
          <QuickAction
            title="Importar CSV"
            description="Suba uma planilha com centenas de contatos de uma vez."
            icon={Upload}
            href="/dashboard/contacts"
          />
          <QuickAction
            title="Ver no mapa"
            description="Visualize a distribuição geográfica dos seus contatos."
            icon={MapPinned}
            href="/dashboard/map"
          />
        </div>
      </section>

      {/* Aniversariantes da semana — widget gabinete/campanha */}
      <BirthdaysCard />

      {/* Insight + Sobre */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Insight de resolução */}
        <div className="lg:col-span-2 rounded-xl border bg-card p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <TrendingUp className="h-4 w-4 text-emerald-600" />
            Performance do gabinete
          </div>
          <div className="mt-4 grid grid-cols-3 gap-4 text-center">
            <StatBlock
              value={stats ? numberFmt.format(stats.demandsResolved) : "—"}
              label="Resolvidas"
              tone="emerald"
            />
            <StatBlock
              value={
                stats
                  ? numberFmt.format(
                      stats.demandsOpen + stats.demandsInProgress,
                    )
                  : "—"
              }
              label="Em aberto"
              tone="amber"
            />
            <StatBlock
              value={
                stats
                  ? `${Math.round(
                      (stats.demandsResolved /
                        Math.max(
                          1,
                          stats.demandsResolved +
                            stats.demandsOpen +
                            stats.demandsInProgress,
                        )) *
                        100,
                    )}%`
                  : "—"
              }
              label="Taxa de resolução"
              tone="brand"
            />
          </div>
        </div>

        {/* Sobre a campanha */}
        <div className="rounded-xl border bg-card p-5">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Sua campanha
          </p>
          {me ? (
            <dl className="mt-3 space-y-2.5 text-sm">
              <Row label="Campanha" value={me.tenant_name} />
              <Row label="Slug" value={me.tenant_slug} mono />
              <Row label="Seu papel" value={roleLabel(me.role)} />
              <Row label="Email" value={me.email} />
            </dl>
          ) : (
            <div className="mt-3 space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-3 w-full bg-muted rounded animate-pulse" />
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
    </PullToRefresh>
  );
}

// ============================================================ Components

function KpiCard({
  label,
  value,
  icon: Icon,
  tone,
  hint,
  href,
}: {
  label: string;
  value: number | undefined;
  icon: LucideIcon;
  tone: "brand" | "amber" | "blue" | "emerald";
  hint?: string;
  href?: string;
}) {
  const TONE = {
    brand:   { bg: "bg-primary/10",   text: "text-primary",     icon: "bg-primary" },
    amber:   { bg: "bg-amber-500/10",   text: "text-amber-400",   icon: "bg-amber-500" },
    blue:    { bg: "bg-blue-500/10",    text: "text-blue-400",    icon: "bg-blue-500" },
    emerald: { bg: "bg-emerald-500/10", text: "text-emerald-400", icon: "bg-emerald-500" },
  }[tone];

  const content = (
    <div className="rounded-xl border bg-card p-4 sm:p-5 transition-all hover:border-foreground/20 hover:shadow-sm h-full">
      <div className="flex items-start justify-between">
        <div
          className={cn(
            "grid h-9 w-9 sm:h-10 sm:w-10 place-items-center rounded-lg text-white",
            TONE.icon,
          )}
        >
          <Icon className="h-4 w-4 sm:h-5 sm:w-5" />
        </div>
        {href && (
          <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        )}
      </div>
      <p className="mt-3 sm:mt-4 text-[10px] sm:text-xs uppercase tracking-wide text-muted-foreground line-clamp-1">
        {label}
      </p>
      <p className="mt-0.5 sm:mt-1 text-2xl sm:text-3xl font-semibold tracking-tight tabular-nums">
        {value === undefined ? (
          <Loader2 className="h-7 w-7 animate-spin text-muted-foreground inline-block" />
        ) : (
          <AnimatedNumber value={value} />
        )}
      </p>
      {hint && <p className="mt-1 text-[11px] sm:text-xs text-muted-foreground line-clamp-2">{hint}</p>}
    </div>
  );

  return href ? (
    <Link href={href} className="group block">
      {content}
    </Link>
  ) : (
    content
  );
}

function OnboardingStep({
  n,
  done,
  title,
  description,
  href,
  icon: Icon,
}: {
  n: number;
  done: boolean;
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
}) {
  return (
    <li>
      <Link
        href={href}
        className={cn(
          "group flex flex-col h-full rounded-xl border p-4 transition-all",
          done
            ? "border-emerald-500/30 bg-emerald-500/[0.06]"
            : "border-border bg-card hover:border-primary hover:shadow-sm",
        )}
      >
        <div className="flex items-center gap-2 mb-2">
          {done ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <Circle className="w-4 h-4 text-muted-foreground shrink-0" />
          )}
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Passo {n}
          </span>
          <Icon className="w-4 h-4 text-primary ml-auto shrink-0" />
        </div>
        <p className={cn("font-medium", done && "line-through opacity-70")}>{title}</p>
        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{description}</p>
        {!done && (
          <span className="mt-2 inline-flex items-center gap-1 text-xs text-primary font-medium">
            Começar <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
          </span>
        )}
      </Link>
    </li>
  );
}

function QuickAction({
  title,
  description,
  icon: Icon,
  href,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-xl border bg-card p-5 transition-all hover:border-primary hover:shadow-sm flex flex-col"
    >
      <div className="flex items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary group-hover:bg-primary group-hover:text-white transition-colors">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <p className="font-medium text-foreground">{title}</p>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {description}
          </p>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0 group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
      </div>
    </Link>
  );
}

function StatBlock({
  value,
  label,
  tone,
}: {
  value: string;
  label: string;
  tone: "brand" | "amber" | "emerald";
}) {
  const color = {
    brand: "text-primary",
    amber: "text-amber-400",
    emerald: "text-emerald-400",
  }[tone];
  return (
    <div>
      <p className={cn("text-3xl font-semibold tracking-tight", color)}>
        {value}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd
        className={cn(
          "text-right truncate min-w-0",
          mono && "font-mono text-xs",
        )}
      >
        {value}
      </dd>
    </div>
  );
}
