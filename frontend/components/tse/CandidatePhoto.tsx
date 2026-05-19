"use client";

/**
 * Foto oficial do candidato (vinda do TSE via /api/v1/tse/candidates/{id}/photo).
 *
 * Estrategia de fallback:
 * 1. Tenta carregar a foto via <img>
 * 2. Se 404 ou erro de rede, esconde a foto e mostra avatar com iniciais
 * 3. Cor do avatar e deterministica pelo numero do partido (consistente entre paginas)
 *
 * O endpoint backend e PUBLICO (sem JWT) — proxia do TSE com cache em disco.
 */
import { useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

const PARTY_COLORS: Record<number, string> = {
  10: "bg-blue-700",      // REPUBLICANOS
  11: "bg-orange-600",    // PP
  12: "bg-red-700",       // PDT
  13: "bg-red-600",       // PT
  14: "bg-cyan-600",      // PTB
  15: "bg-emerald-700",   // MDB
  17: "bg-yellow-600",    // PSL/UNIAO
  19: "bg-amber-600",     // PODE/PTC
  20: "bg-sky-700",       // PSC
  22: "bg-blue-600",      // PL
  23: "bg-indigo-700",    // CIDADANIA
  25: "bg-blue-800",      // UNIAO
  27: "bg-emerald-600",   // DC
  28: "bg-pink-600",      // PRTB/AVANTE
  30: "bg-fuchsia-600",   // NOVO
  35: "bg-orange-700",    // PMB
  36: "bg-purple-600",    // PTC
  40: "bg-rose-600",      // PSB
  43: "bg-green-700",     // PV
  44: "bg-yellow-700",    // PRP/UNIAO
  45: "bg-cyan-700",      // PSDB
  50: "bg-red-800",       // PSOL
  51: "bg-amber-700",     // PATRIOTA
  54: "bg-emerald-800",   // PPL
  55: "bg-teal-600",      // PSD
  65: "bg-rose-700",      // PCdoB
  70: "bg-orange-800",    // AVANTE
  77: "bg-violet-700",    // SOLIDARIEDADE
  80: "bg-stone-600",     // REDE/AGIR
  90: "bg-slate-600",     // PROS
};

function initials(name: string): string {
  const parts = name
    .replace(/[^a-zA-ZÀ-ÿ ]/g, "")
    .trim()
    .split(/\s+/)
    .filter((p) => p.length > 1);
  if (parts.length === 0) return "??";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

type Size = "sm" | "md" | "lg" | "xl";

const SIZE_PX: Record<Size, string> = {
  sm: "w-10 h-10 text-xs",
  md: "w-14 h-14 text-sm",
  lg: "w-20 h-20 text-base",
  xl: "w-32 h-32 text-2xl",
};

type Props = {
  candidateId: string;
  name: string;
  partyNumber: number;
  size?: Size;
  className?: string;
};

export function CandidatePhoto({
  candidateId,
  name,
  partyNumber,
  size = "md",
  className = "",
}: Props) {
  const [failed, setFailed] = useState(false);
  const dim = SIZE_PX[size];
  const url = `${API_BASE}/v1/tse/candidates/${candidateId}/photo`;
  const color = PARTY_COLORS[partyNumber] ?? "bg-slate-600";

  if (failed) {
    return (
      <div
        className={`shrink-0 ${dim} rounded-full ${color} grid place-items-center font-bold text-white ${className}`}
        title={name}
      >
        {initials(name)}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt={name}
      onError={() => setFailed(true)}
      loading="lazy"
      className={`shrink-0 ${dim} rounded-full object-cover bg-card border border-border ${className}`}
    />
  );
}
