/**
 * color-hash — cor determinística a partir de um texto (nome, tag).
 *
 * Usado por avatares de contato e chips de tag: o mesmo nome SEMPRE cai na
 * mesma cor, sem estado nem storage. Paleta com ~8 pares bg/texto escolhidos
 * pra funcionar nos DOIS temas (bg translúcido /15 + texto 600 no claro e
 * 400 no escuro).
 *
 * ATENÇÃO (Tailwind): o `content` do tailwind.config.ts NÃO varre lib/ —
 * estas classes só são geradas porque estão listadas no bloco-safelist de
 * components/contacts/ContactAvatar.tsx. Ao adicionar um tom novo aqui,
 * replique as classes lá.
 */

export type ColorPair = {
  /** Fundo translúcido (funciona sobre card claro e escuro). */
  bg: string;
  /** Texto: tom 600 no tema claro, 400 no escuro (contraste AA). */
  text: string;
  /** Borda sutil no mesmo matiz (pra chips/tags). */
  border: string;
};

const PALETTE: ColorPair[] = [
  { bg: "bg-rose-500/15", text: "text-rose-600 dark:text-rose-400", border: "border-rose-500/25" },
  { bg: "bg-emerald-500/15", text: "text-emerald-600 dark:text-emerald-400", border: "border-emerald-500/25" },
  { bg: "bg-sky-500/15", text: "text-sky-600 dark:text-sky-400", border: "border-sky-500/25" },
  { bg: "bg-amber-500/15", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/25" },
  { bg: "bg-violet-500/15", text: "text-violet-600 dark:text-violet-400", border: "border-violet-500/25" },
  { bg: "bg-teal-500/15", text: "text-teal-600 dark:text-teal-400", border: "border-teal-500/25" },
  { bg: "bg-orange-500/15", text: "text-orange-600 dark:text-orange-400", border: "border-orange-500/25" },
  { bg: "bg-fuchsia-500/15", text: "text-fuchsia-600 dark:text-fuchsia-400", border: "border-fuchsia-500/25" },
];

/**
 * Hash simples (multiplicador 31, estilo Java) → índice estável na paleta.
 * `>>> 0` mantém o acumulador como uint32 (evita negativo no módulo).
 */
export function hashColor(name: string): ColorPair {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) >>> 0;
  }
  return PALETTE[h % PALETTE.length];
}
