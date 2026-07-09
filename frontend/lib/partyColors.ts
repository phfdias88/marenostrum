/**
 * Cores de partido brasileiro — FONTE CANÔNICA ÚNICA.
 *
 * Número eleitoral do partido → hex da cor mais reconhecível da marca.
 * Números de partidos extintos permanecem no mapa porque a base histórica
 * (2002-2024) ainda os referencia.
 *
 * NÃO duplique este mapa em componentes — importe `partyColor()` daqui.
 */

export const PARTY_COLOR: Record<number, string> = {
  10: "#0050a0", // REPUBLICANOS
  11: "#ff8c00", // PP (Progressistas)
  12: "#c41a1a", // PDT
  13: "#e30613", // PT
  14: "#0099cc", // PTB (extinto em 2023 → PRD)
  15: "#2d6f30", // MDB
  16: "#a31a1a", // PSTU
  17: "#ffcd1a", // PSL (extinto em 2022 → UNIÃO, 44)
  18: "#7fbc41", // REDE
  // PODE em petróleo escuro (não o #00a99d oficial): o PSD (55) já usa esse
  // teal em todo o app e os dois ficariam indistinguíveis no mapa partidário.
  19: "#0d6f7e", // PODE — número antigo (ex-PTN); desde 2023 o partido usa o 20
  20: "#0d6f7e", // PODE (POD) — número atual, herdado ao incorporar o PSC
  22: "#0a2a7d", // PL
  23: "#3f51b5", // CIDADANIA
  25: "#0050a0", // DEM (extinto em 2022 → UNIÃO, 44); em 2024 o 25 é do PRD
  27: "#27ae60", // DC (Democracia Cristã)
  28: "#e91e63", // PRTB
  30: "#ff4e00", // NOVO (laranja oficial)
  31: "#9b59b6", // PHS (extinto em 2019 → PODE)
  33: "#0d47a1", // PMN (hoje Mobiliza)
  35: "#c97312", // PMB
  36: "#7b1fa2", // AGIR (ex-PTC)
  40: "#d81b60", // PSB
  43: "#1e8a3c", // PV
  44: "#ed9b00", // UNIÃO BRASIL
  45: "#0059ab", // PSDB (azul tucano oficial)
  50: "#dc143c", // PSOL
  51: "#1c8537", // PATRIOTA (extinto em 2023 → PRD)
  54: "#0c6e3e", // PPL (extinto em 2019 → PCdoB)
  55: "#00a99d", // PSD
  65: "#cc0000", // PCdoB
  70: "#d35400", // AVANTE (ex-PTdoB)
  77: "#673ab7", // SOLIDARIEDADE
  80: "#6b6b6b", // UP (Unidade Popular)
  90: "#37474f", // PROS (extinto em 2023 → SOLIDARIEDADE)
};

/** Cor do partido pelo número eleitoral; fallback neutro p/ desconhecido. */
export function partyColor(n?: number | null): string {
  return (n != null ? PARTY_COLOR[n] : undefined) ?? "#888";
}

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
