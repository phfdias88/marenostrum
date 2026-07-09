"use client";

/**
 * Logo de partido brasileiro — 2 niveis:
 *  1. /party-logos/{numero}.png  (logo OFICIAL, se o arquivo existir em public/)
 *  2. SVG badge gerado (numero + sigla + cor da marca) — fallback consistente
 *
 * Logos oficiais sao copyrightados (sem CDN livre confiavel), entao o caminho
 * recomendado e dropar os PNGs em frontend/public/party-logos/. Ate la, o badge
 * cobre 100% dos partidos com visual limpo e legal.
 */
import { useId, useState } from "react";

import { darkenHex, partyColor, readableTextOn } from "@/lib/partyColors";

type Size = "sm" | "md" | "lg" | "xl";

const DIM: Record<Size, { px: number; numFont: number; sigFont: number }> = {
  sm: { px: 40, numFont: 16, sigFont: 7 },
  md: { px: 56, numFont: 22, sigFont: 9 },
  lg: { px: 80, numFont: 30, sigFont: 12 },
  xl: { px: 128, numFont: 48, sigFont: 18 },
};

// Tema do badge derivado da cor canonica do partido (lib/partyColors):
// fundo = cor da marca, ring = fundo escurecido, texto = preto/branco legivel.
// Hex direto porque Tailwind nao funciona dentro de attrs de SVG.
function themeFor(partyNumber: number): { bg: string; ring: string; text: string } {
  const bg = partyColor(partyNumber);
  return { bg, ring: darkenHex(bg), text: readableTextOn(bg) };
}

type Props = {
  number: number;
  abbreviation: string;
  size?: Size;
  showAbbr?: boolean; // default true
  className?: string;
};

export function PartyLogo({
  number,
  abbreviation,
  size = "md",
  showAbbr = true,
  className = "",
}: Props) {
  const { px, numFont, sigFont } = DIM[size];
  const theme = themeFor(number);
  const gradId = useId();
  const [imgFailed, setImgFailed] = useState(false);

  // Tier 1: logo oficial em public/party-logos/{numero}.png.
  // Gateado por NEXT_PUBLIC_PARTY_LOGOS=1 (build arg) — sem isso, vai direto
  // pro badge e evita 29x 404 por render enquanto os PNGs nao existem.
  const logosEnabled = process.env.NEXT_PUBLIC_PARTY_LOGOS === "1";
  if (logosEnabled && !imgFailed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={`/party-logos/${number}.png`}
        alt={abbreviation}
        title={`${abbreviation} (${number})`}
        loading="lazy"
        onError={() => setImgFailed(true)}
        style={{ width: px, height: px }}
        className={`shrink-0 object-contain rounded-md bg-white/95 p-1 ${className}`}
      />
    );
  }

  // Trunca sigla muito longa (ex: REPUBLICANOS)
  const sigla =
    abbreviation.length > 7 ? abbreviation.slice(0, 6) + "·" : abbreviation;

  return (
    <svg
      width={px}
      height={px}
      viewBox="0 0 100 100"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={`Logo ${abbreviation} (${number})`}
      className={`shrink-0 ${className}`}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={theme.bg} />
          <stop offset="100%" stopColor={theme.ring} />
        </linearGradient>
      </defs>
      {/* Circulo externo com gradient + sombra de profundidade via ring escuro */}
      <circle cx="50" cy="50" r="48" fill={`url(#${gradId})`} />
      <circle
        cx="50"
        cy="50"
        r="48"
        fill="none"
        stroke={theme.ring}
        strokeWidth="1.5"
      />
      {/* Numero grande no centro */}
      <text
        x="50"
        y={showAbbr ? 47 : 58}
        textAnchor="middle"
        fontFamily="system-ui, sans-serif"
        fontWeight="800"
        fontSize={numFont}
        fill={theme.text}
      >
        {number}
      </text>
      {/* Sigla abaixo */}
      {showAbbr && (
        <text
          x="50"
          y="72"
          textAnchor="middle"
          fontFamily="system-ui, sans-serif"
          fontWeight="700"
          fontSize={sigFont}
          fill={theme.text}
          opacity="0.92"
          letterSpacing="0.4"
        >
          {sigla}
        </text>
      )}
    </svg>
  );
}
