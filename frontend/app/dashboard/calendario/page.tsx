"use client";

/**
 * /dashboard/calendario — calendário eleitoral 2026 com checklist.
 *
 * - Timeline com datas-chave do TSE (convenções, registro, propaganda,
 *   debate, 1º/2º turno, prestação de contas, diplomação, posse)
 * - Checkbox por item (state em localStorage por slug)
 * - Próximo evento destacado com countdown
 * - Filtrar por fase
 */
import { AlertTriangle, ArrowLeft, Calendar, Check } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  CALENDARIO_2026,
  type CalendarItem,
  type CalendarPhase,
} from "@/lib/calendario2026";

const STORAGE_KEY = "mn:calendario:done:v1";

const PHASE_LABELS: Record<CalendarPhase, string> = {
  "pre-campanha": "Pré-campanha",
  campanha: "Campanha",
  "pos-campanha": "Pós-campanha",
};

const PHASE_TONES: Record<CalendarPhase, string> = {
  "pre-campanha": "bg-blue-500/15 text-blue-700",
  campanha: "bg-primary/15 text-primary",
  "pos-campanha": "bg-emerald-500/15 text-emerald-700",
};

function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

export default function CalendarioPage() {
  const [done, setDone] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<CalendarPhase | "all">("all");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setDone(new Set(JSON.parse(raw)));
    } catch {
      /* ignore */
    }
  }, []);

  function toggle(slug: string) {
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(next)));
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  const now = useMemo(() => new Date(), []);

  const items = useMemo(() => {
    const all = CALENDARIO_2026.filter((i) => filter === "all" || i.phase === filter);
    return all;
  }, [filter]);

  const nextItem = useMemo(() => {
    return CALENDARIO_2026.find((i) => {
      const [y, m, d] = i.date.split("-").map(Number);
      return new Date(y, m - 1, d) >= now && !done.has(i.slug);
    });
  }, [now, done]);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="my-6">
        <h1 className="text-2xl font-bold inline-flex items-center gap-2">
          <Calendar className="w-6 h-6 text-primary" /> Calendário eleitoral 2026
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Datas-chave do TSE pra eleições gerais (Presidente, Governador,
          Senador, Deputados). Marque os itens conforme conclui.
        </p>
      </header>

      {nextItem && (
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 mb-6">
          <p className="text-xs uppercase tracking-wider text-primary mb-1">
            Próximo evento
          </p>
          <p className="font-semibold">{nextItem.title}</p>
          <p className="text-sm text-muted-foreground">
            {fmtDate(nextItem.date)} ·{" "}
            <strong>
              {(() => {
                const [y, m, d] = nextItem.date.split("-").map(Number);
                const days = daysBetween(now, new Date(y, m - 1, d));
                return days === 0 ? "Hoje" : days === 1 ? "Amanhã" : `Em ${days} dias`;
              })()}
            </strong>
          </p>
        </div>
      )}

      {/* Filtro por fase */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {(["all", "pre-campanha", "campanha", "pos-campanha"] as const).map((f) => {
          const on = filter === f;
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                on
                  ? "border-primary bg-primary/15 text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-primary/50"
              }`}
            >
              {f === "all" ? "Tudo" : PHASE_LABELS[f]}
            </button>
          );
        })}
      </div>

      {/* Timeline */}
      <ol className="relative space-y-3">
        {items.map((item) => {
          const [y, m, d] = item.date.split("-").map(Number);
          const dt = new Date(y, m - 1, d);
          const days = daysBetween(now, dt);
          const isPast = days < 0;
          const isDone = done.has(item.slug);
          return (
            <li
              key={item.slug}
              className={`rounded-xl border p-4 transition-colors ${
                isDone
                  ? "bg-card/40 border-emerald-500/30"
                  : isPast
                    ? "bg-card/30 border-border opacity-60"
                    : "bg-card border-border"
              }`}
            >
              <div className="flex items-start gap-3">
                <button
                  onClick={() => toggle(item.slug)}
                  className={`mt-0.5 h-5 w-5 shrink-0 rounded border-2 flex items-center justify-center transition-colors ${
                    isDone
                      ? "border-emerald-500 bg-emerald-500"
                      : "border-border hover:border-primary"
                  }`}
                  aria-label={isDone ? "Desmarcar" : "Marcar como concluído"}
                >
                  {isDone && <Check className="w-3 h-3 text-white" />}
                </button>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${PHASE_TONES[item.phase]}`}
                    >
                      {PHASE_LABELS[item.phase].toUpperCase()}
                    </span>
                    {item.tentative && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] font-medium text-amber-700">
                        <AlertTriangle className="w-2.5 h-2.5" /> Estimada
                      </span>
                    )}
                  </div>
                  <p
                    className={`font-semibold mt-1 ${isDone ? "line-through text-muted-foreground" : ""}`}
                  >
                    {item.title}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                    {item.description}
                  </p>
                  <p className="text-xs mt-1.5 font-mono">
                    {fmtDate(item.date)}
                    <span className="ml-2 text-muted-foreground">
                      {isPast
                        ? `há ${Math.abs(days)} dias`
                        : days === 0
                          ? "hoje"
                          : `em ${days} dias`}
                    </span>
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <p
        className="text-[11px] text-muted-foreground mt-6 text-center"
        title="Fontes: Lei 9.504/97 + Resoluções TSE 23.610/2019, 23.671/2021, 23.675/2021."
      >
        Datas baseadas na legislação eleitoral e em resoluções do TSE. Itens
        marcados como &quot;Estimada&quot; aguardam publicação da Resolução TSE
        2026.
      </p>
    </div>
  );
}
