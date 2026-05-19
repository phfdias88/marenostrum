"use client";

/**
 * Badge do resultado eleitoral do candidato (ELEITO / NÃO ELEITO / etc).
 * Cor + icone por categoria.
 */
import { Check, Clock, Minus, X } from "lucide-react";

import { classifyResult, OUTCOME_LABEL } from "@/lib/types";

const STYLES: Record<
  string,
  { cls: string; icon: React.ReactNode }
> = {
  elected: {
    cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    icon: <Check className="w-3 h-3" />,
  },
  runoff: {
    cls: "bg-blue-500/15 text-blue-400 border-blue-500/30",
    icon: <Clock className="w-3 h-3" />,
  },
  alternate: {
    cls: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    icon: <Minus className="w-3 h-3" />,
  },
  not_elected: {
    cls: "bg-slate-500/15 text-slate-400 border-slate-500/30",
    icon: <X className="w-3 h-3" />,
  },
  unknown: {
    cls: "bg-muted text-muted-foreground border-border",
    icon: null,
  },
};

type Props = {
  status: string | null;
  size?: "sm" | "md";
  /** Mostra o texto bruto do TSE no title (hover) */
  showRaw?: boolean;
};

export function ResultBadge({ status, size = "md", showRaw = true }: Props) {
  const outcome = classifyResult(status);
  if (outcome === "unknown" && !status) return null;
  const { cls, icon } = STYLES[outcome];
  const pad = size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border font-semibold ${pad} ${cls}`}
      title={showRaw && status ? status : undefined}
    >
      {icon}
      {OUTCOME_LABEL[outcome]}
    </span>
  );
}
