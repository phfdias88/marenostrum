"use client";

/**
 * Logo visual de partido brasileiro.
 *
 * Decisao: gerar inline SVG com cor de marca do partido + numero grande
 * + sigla — em vez de depender de PNGs externos com licencas variaveis.
 * Resultado: 30 partidos com identidade visual consistente, zero bytes
 * extras na rede, escala perfeita em qualquer tamanho.
 *
 * Cores baseadas nas oficiais ou tradicionalmente associadas a cada partido.
 */
import { useId } from "react";

type Size = "sm" | "md" | "lg" | "xl";

const DIM: Record<Size, { px: number; numFont: number; sigFont: number }> = {
  sm: { px: 40, numFont: 16, sigFont: 7 },
  md: { px: 56, numFont: 22, sigFont: 9 },
  lg: { px: 80, numFont: 30, sigFont: 12 },
  xl: { px: 128, numFont: 48, sigFont: 18 },
};

// Cor primaria (fundo) e secundaria (acento) por numero de partido
// Hex pra serem usados diretamente no SVG (Tailwind nao funciona dentro de attrs)
const PARTY_THEME: Record<number, { bg: string; ring: string; text: string }> = {
  10: { bg: "#0050a0", ring: "#003776", text: "#ffffff" }, // REPUBLICANOS azul
  11: { bg: "#ff8c00", ring: "#cc6f00", text: "#ffffff" }, // PP laranja
  12: { bg: "#c41a1a", ring: "#8a1313", text: "#ffffff" }, // PDT vermelho
  13: { bg: "#e30613", ring: "#ad0410", text: "#ffffff" }, // PT vermelho-classico
  14: { bg: "#0099cc", ring: "#006e91", text: "#ffffff" }, // PTB
  15: { bg: "#2d6f30", ring: "#1d4e1f", text: "#ffffff" }, // MDB verde
  16: { bg: "#a31a1a", ring: "#741212", text: "#ffffff" }, // PSTU
  17: { bg: "#ffcd1a", ring: "#cc9d0a", text: "#1a1a1a" }, // PSL/UNIAO amarelo
  18: { bg: "#7fbc41", ring: "#5c8a30", text: "#1a1a1a" }, // REDE verde-claro
  19: { bg: "#16a085", ring: "#0e6b59", text: "#ffffff" }, // PODE
  20: { bg: "#1f5fa6", ring: "#143d6b", text: "#ffffff" }, // PSC
  22: { bg: "#0a2a7d", ring: "#061854", text: "#ffffff" }, // PL azul-marinho
  23: { bg: "#3f51b5", ring: "#2c3a82", text: "#ffffff" }, // CIDADANIA
  25: { bg: "#0050a0", ring: "#003776", text: "#ffffff" }, // UNIAO azul
  27: { bg: "#27ae60", ring: "#1a7a43", text: "#ffffff" }, // DC verde
  28: { bg: "#e91e63", ring: "#a31548", text: "#ffffff" }, // AVANTE
  30: { bg: "#ff5a00", ring: "#cc4500", text: "#ffffff" }, // NOVO laranja
  31: { bg: "#9b59b6", ring: "#6c3d80", text: "#ffffff" }, // PMN
  33: { bg: "#0d47a1", ring: "#072c64", text: "#ffffff" }, // PMB azul
  35: { bg: "#c97312", ring: "#8e500c", text: "#ffffff" }, // PMB/PRP
  36: { bg: "#7b1fa2", ring: "#54156f", text: "#ffffff" }, // PTC
  40: { bg: "#d81b60", ring: "#9c1245", text: "#ffffff" }, // PSB
  43: { bg: "#1e8a3c", ring: "#13602a", text: "#ffffff" }, // PV verde
  44: { bg: "#ed9b00", ring: "#a86c00", text: "#ffffff" }, // UNIAO laranja
  45: { bg: "#005faa", ring: "#003e70", text: "#ffffff" }, // PSDB azul-tucano
  50: { bg: "#dc143c", ring: "#8c0c25", text: "#ffffff" }, // PSOL
  51: { bg: "#1c8537", ring: "#125724", text: "#ffffff" }, // PATRIOTA
  54: { bg: "#0c6e3e", ring: "#08502c", text: "#ffffff" }, // PPL
  55: { bg: "#00a99d", ring: "#007a71", text: "#ffffff" }, // PSD turquesa
  65: { bg: "#cc0000", ring: "#8a0000", text: "#ffffff" }, // PCdoB
  70: { bg: "#d35400", ring: "#963c00", text: "#ffffff" }, // AVANTE
  77: { bg: "#673ab7", ring: "#48287d", text: "#ffffff" }, // SOLIDARIEDADE
  80: { bg: "#6b6b6b", ring: "#4a4a4a", text: "#ffffff" }, // REDE/AGIR
  90: { bg: "#37474f", ring: "#1f2a30", text: "#ffffff" }, // PROS
};

const FALLBACK = { bg: "#475569", ring: "#1e293b", text: "#ffffff" };

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
  const theme = PARTY_THEME[number] ?? FALLBACK;
  const gradId = useId();

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
