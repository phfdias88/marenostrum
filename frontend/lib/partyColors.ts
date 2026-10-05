/**
 * Cor + tema visual de partido brasileiro — FONTE CANÔNICA ÚNICA.
 *
 * Guarda o tema CURADO (fundo, anel/borda e cor de texto escolhidos à mão) que
 * o app usava antes da consolidação. O derivado algorítmico (ring=darkenHex,
 * texto=luminância) deixava badges feios (texto escuro sobre laranja/âmbar,
 * PODE em petróleo) — voltamos aos valores bonitos, mantendo 1 fonte só (DRY).
 *
 * NÃO duplique estes valores em componentes — importe partyColor()/partyTheme().
 */
export type PartyTheme = {
  /** Cor da marca (fundo do badge, ponto no mapa). */
  color: string;
  /** Anel/borda do badge — tom mais escuro da marca. */
  ring: string;
  /** Cor de texto legível sobre `color` (#fff ou quase-preto). */
  text: string;
};

const FALLBACK: PartyTheme = { color: "#475569", ring: "#1e293b", text: "#ffffff" };

// Número eleitoral → tema. Partidos extintos permanecem (a base histórica
// 2002-2024 os referencia).
export const PARTY_THEME: Record<number, PartyTheme> = {
  10: { color: "#0050a0", ring: "#003776", text: "#ffffff" }, // REPUBLICANOS azul
  11: { color: "#ff8c00", ring: "#cc6f00", text: "#ffffff" }, // PP laranja
  12: { color: "#c41a1a", ring: "#8a1313", text: "#ffffff" }, // PDT vermelho
  13: { color: "#e30613", ring: "#ad0410", text: "#ffffff" }, // PT vermelho-clássico
  14: { color: "#0099cc", ring: "#006e91", text: "#ffffff" }, // PTB (extinto→PRD)
  15: { color: "#2d6f30", ring: "#1d4e1f", text: "#ffffff" }, // MDB verde
  16: { color: "#a31a1a", ring: "#741212", text: "#ffffff" }, // PSTU
  17: { color: "#ffcd1a", ring: "#cc9d0a", text: "#1a1a1a" }, // PSL (extinto→UNIÃO) amarelo
  18: { color: "#7fbc41", ring: "#5c8a30", text: "#1a1a1a" }, // REDE verde-claro
  19: { color: "#16a085", ring: "#0e6b59", text: "#ffffff" }, // PODE (nº antigo) teal-verde
  20: { color: "#1f5fa6", ring: "#143d6b", text: "#ffffff" }, // PODE (nº atual, ex-PSC) azul
  22: { color: "#0a2a7d", ring: "#061854", text: "#ffffff" }, // PL azul-marinho
  23: { color: "#3f51b5", ring: "#2c3a82", text: "#ffffff" }, // CIDADANIA
  25: { color: "#0050a0", ring: "#003776", text: "#ffffff" }, // DEM (extinto→UNIÃO); 2024 = PRD
  27: { color: "#27ae60", ring: "#1a7a43", text: "#ffffff" }, // DC verde
  28: { color: "#e91e63", ring: "#a31548", text: "#ffffff" }, // PRTB
  30: { color: "#ff5a00", ring: "#cc4500", text: "#ffffff" }, // NOVO laranja
  31: { color: "#9b59b6", ring: "#6c3d80", text: "#ffffff" }, // PHS (extinto→PODE)
  33: { color: "#0d47a1", ring: "#072c64", text: "#ffffff" }, // PMN azul
  35: { color: "#c97312", ring: "#8e500c", text: "#ffffff" }, // PMB
  36: { color: "#7b1fa2", ring: "#54156f", text: "#ffffff" }, // AGIR (ex-PTC)
  40: { color: "#d81b60", ring: "#9c1245", text: "#ffffff" }, // PSB
  43: { color: "#1e8a3c", ring: "#13602a", text: "#ffffff" }, // PV verde
  44: { color: "#ed9b00", ring: "#a86c00", text: "#ffffff" }, // UNIÃO BRASIL laranja
  45: { color: "#005faa", ring: "#003e70", text: "#ffffff" }, // PSDB azul-tucano
  50: { color: "#dc143c", ring: "#8c0c25", text: "#ffffff" }, // PSOL
  51: { color: "#1c8537", ring: "#125724", text: "#ffffff" }, // PATRIOTA (extinto→PRD)
  54: { color: "#0c6e3e", ring: "#08502c", text: "#ffffff" }, // PPL (extinto→PCdoB)
  55: { color: "#00a99d", ring: "#007a71", text: "#ffffff" }, // PSD turquesa
  65: { color: "#cc0000", ring: "#8a0000", text: "#ffffff" }, // PCdoB
  70: { color: "#d35400", ring: "#963c00", text: "#ffffff" }, // AVANTE (ex-PTdoB)
  77: { color: "#673ab7", ring: "#48287d", text: "#ffffff" }, // SOLIDARIEDADE
  80: { color: "#6b6b6b", ring: "#4a4a4a", text: "#ffffff" }, // UP
  90: { color: "#37474f", ring: "#1f2a30", text: "#ffffff" }, // PROS (extinto→SOLIDARIEDADE)
};

/** Tema completo (cor/anel/texto) pelo número; fallback neutro p/ desconhecido. */
export function partyTheme(n?: number | null): PartyTheme {
  return (n != null ? PARTY_THEME[n] : undefined) ?? FALLBACK;
}

/** Só a cor da marca pelo número (fundo/ponto no mapa). */
export function partyColor(n?: number | null): string {
  return partyTheme(n).color;
}

/** Mapa número→cor (compat p/ quem só quer a cor). */
export const PARTY_COLOR: Record<number, string> = Object.fromEntries(
  Object.entries(PARTY_THEME).map(([k, v]) => [Number(k), v.color]),
) as Record<number, string>;

function channels(hex: string): [number, number, number] {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

/** Escurece um hex multiplicando cada canal RGB por `factor` (0..1). */
export function darkenHex(hex: string, factor = 0.7): string {
  const [r, g, b] = channels(hex).map((c) =>
    Math.max(0, Math.min(255, Math.round(c * factor))),
  );
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

/** Cor de texto (quase-preto ou branco) legível sobre o hex dado. */
export function readableTextOn(hex: string): string {
  const [r, g, b] = channels(hex);
  const luma = 0.299 * r + 0.587 * g + 0.114 * b;
  return luma > 150 ? "#1a1a1a" : "#ffffff";
}
