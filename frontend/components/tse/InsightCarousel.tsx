"use client";

/**
 * Hero rotativo da /dashboard — carrossel de "insights" puxados dos
 * endpoints TSE existentes. Auto-rotate, fade smooth, dots e setas
 * pra navegar. Funciona em light/dark via vidro fosco gold.
 *
 * Cada slide e um Link clicavel pra pagina relacionada.
 */
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Crown,
  MapPinned,
  TrendingUp,
  Vote,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type {
  TsePartyPerformanceResponse,
  TseTopCandidatesResponse,
} from "@/lib/types";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";

type Slide = {
  kicker: string;
  title: string;
  subtitle: string;
  metric?: { value: number; label: string; suffix?: string; prefix?: string };
  cta: { label: string; href: string };
  icon: LucideIcon;
  /** Tom destacado (degrade do fundo do slide). */
  tone: "gold" | "emerald" | "blue" | "rose";
};

const FALLBACK: Slide[] = [
  {
    kicker: "Inteligência eleitoral",
    title: "Explore o cenário eleitoral brasileiro",
    subtitle: "454 mil candidatos, 5.571 municípios, votos por bairro e zona.",
    cta: { label: "Abrir Análises", href: "/dashboard/analises" },
    icon: Vote,
    tone: "gold",
  },
];

function toneClasses(t: Slide["tone"]) {
  switch (t) {
    case "emerald":
      return "from-emerald-500/15 via-card to-card";
    case "blue":
      return "from-blue-500/15 via-card to-card";
    case "rose":
      return "from-rose-500/15 via-card to-card";
    default:
      return "from-primary/20 via-card to-card";
  }
}

function iconBg(t: Slide["tone"]) {
  switch (t) {
    case "emerald":
      return "bg-emerald-500/15 text-emerald-400";
    case "blue":
      return "bg-blue-500/15 text-blue-400";
    case "rose":
      return "bg-rose-500/15 text-rose-400";
    default:
      return "bg-primary/15 text-primary";
  }
}

export function InsightCarousel() {
  const [slides, setSlides] = useState<Slide[]>(FALLBACK);
  const [active, setActive] = useState(0);

  useEffect(() => {
    // As 2 chamadas saem em PARALELO; montamos os slides numa passada só
    // (1 re-render, ordem determinística — antes cada .then re-renderizava
    // e a ordem dos slides dependia de qual resposta chegava primeiro).
    Promise.allSettled([
      api<TseTopCandidatesResponse>(
        "/v1/tse/stats/top-candidates?year=2024&office_code=11&elected_only=true&limit=1",
      ),
      api<TsePartyPerformanceResponse>(
        "/v1/tse/stats/party-performance?year=2024&office_code=11",
      ),
    ]).then(([topRes, partyRes]) => {
      const next: Slide[] = [];
      if (topRes.status === "fulfilled" && topRes.value.items[0]) {
        const it = topRes.value.items[0];
        next.push({
          kicker: "Candidato em destaque",
          title: it.candidate.urn_name,
          subtitle: `${it.candidate.party.abbreviation} · ${it.candidate.office_name} · ${it.candidate.state}`,
          metric: { value: it.total_votes, label: "votos nominais" },
          cta: {
            label: "Ver candidato",
            href: `/dashboard/analises/candidato/${it.candidate.id}`,
          },
          icon: Crown,
          tone: "gold",
        });
      }
      next.push(...FALLBACK);
      if (partyRes.status === "fulfilled" && partyRes.value.items[0]) {
        const it = partyRes.value.items[0];
        next.push({
          kicker: "Partido em alta",
          title: `${it.party.abbreviation} lidera prefeituras 2024`,
          subtitle: `${it.party.name}`,
          metric: { value: it.elected_count, label: "prefeitos eleitos" },
          cta: {
            label: "Ver partido",
            href: `/dashboard/analises/partido/${it.party.number}`,
          },
          icon: TrendingUp,
          tone: "emerald",
        });
      }
      next.push({
        kicker: "Visualização",
        title: "Brasil colorido por partido vencedor",
        subtitle: "Veja o mapa nacional pintado pelo partido que venceu cada cidade.",
        cta: { label: "Abrir mapa", href: "/dashboard/analises/mapa" },
        icon: MapPinned,
        tone: "blue",
      });
      setSlides(next);
    });
  }, []);

  // Auto-rotate
  useEffect(() => {
    if (slides.length <= 1) return;
    const id = setInterval(() => setActive((a) => (a + 1) % slides.length), 6500);
    return () => clearInterval(id);
  }, [slides.length]);

  const slide = slides[active] ?? slides[0];
  const Icon = slide.icon;

  // Swipe touch handlers — desliza pra esquerda/direita no mobile
  const touchStartX = useRef<number | null>(null);
  const touchEndX = useRef<number | null>(null);
  function onTouchStart(e: React.TouchEvent) {
    touchEndX.current = null;
    touchStartX.current = e.targetTouches[0].clientX;
  }
  function onTouchMove(e: React.TouchEvent) {
    touchEndX.current = e.targetTouches[0].clientX;
  }
  function onTouchEnd() {
    if (touchStartX.current == null || touchEndX.current == null) return;
    const dx = touchStartX.current - touchEndX.current;
    const THRESHOLD = 50;
    if (Math.abs(dx) > THRESHOLD && slides.length > 1) {
      if (dx > 0) setActive((a) => (a + 1) % slides.length);
      else setActive((a) => (a - 1 + slides.length) % slides.length);
    }
    touchStartX.current = null;
    touchEndX.current = null;
  }

  return (
    <div className="relative">
      <div
        key={active}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        className={
          "relative overflow-hidden rounded-2xl border bg-gradient-to-br touch-pan-y " +
          toneClasses(slide.tone) +
          " mn-slide-in"
        }
      >
        {/* glow no canto */}
        <div className="absolute -right-12 -top-12 w-56 h-56 rounded-full bg-primary/10 blur-3xl pointer-events-none" />

        <div className="relative p-5 sm:p-6 pb-9 sm:pb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 sm:gap-6">
          <div className="flex items-start gap-4 min-w-0 flex-1">
            <div
              className={
                "grid place-items-center w-12 h-12 rounded-xl shrink-0 " +
                iconBg(slide.tone)
              }
            >
              <Icon className="w-6 h-6" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">
                {slide.kicker}
              </p>
              <h2 className="text-lg sm:text-2xl font-bold mt-0.5 leading-tight">
                {slide.title}
              </h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                {slide.subtitle}
              </p>
              {slide.metric && (
                <p className="text-sm mt-2">
                  <span className="text-2xl font-bold text-primary tabular-nums mr-1.5">
                    <AnimatedNumber
                      value={slide.metric.value}
                      prefix={slide.metric.prefix}
                      suffix={slide.metric.suffix}
                    />
                  </span>
                  <span className="text-muted-foreground">{slide.metric.label}</span>
                </p>
              )}
            </div>
          </div>

          <Link
            href={slide.cta.href}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground font-medium hover:gap-3 transition-all w-full sm:w-auto sm:shrink-0"
          >
            {slide.cta.label} <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Controles (so quando ha mais de 1 slide) */}
        {slides.length > 1 && (
          <>
            <button
              aria-label="Anterior"
              onClick={() => setActive((a) => (a - 1 + slides.length) % slides.length)}
              data-no-mobile-touch
              className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 min-h-0 grid place-items-center rounded-full bg-card/70 backdrop-blur border border-border hover:bg-card transition-colors opacity-0 hover:opacity-100 focus:opacity-100 sm:opacity-60 sm:hover:opacity-100"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              aria-label="Próximo"
              onClick={() => setActive((a) => (a + 1) % slides.length)}
              data-no-mobile-touch
              className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 min-h-0 grid place-items-center rounded-full bg-card/70 backdrop-blur border border-border hover:bg-card transition-colors opacity-0 hover:opacity-100 focus:opacity-100 sm:opacity-60 sm:hover:opacity-100"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            {/* Dots */}
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex items-center gap-1.5">
              {slides.map((_, i) => (
                <button
                  key={i}
                  aria-label={`Ir para slide ${i + 1}`}
                  onClick={() => setActive(i)}
                  data-no-mobile-touch
                  className={
                    "h-1.5 rounded-full transition-all " +
                    (i === active
                      ? "w-6 bg-primary"
                      : "w-1.5 bg-muted-foreground/40 hover:bg-muted-foreground/70")
                  }
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
