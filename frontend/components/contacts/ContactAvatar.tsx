"use client";

/**
 * ContactAvatar — avatar de iniciais com cor determinística pelo nome.
 *
 * Sem foto de contato no CRM, as iniciais coloridas dão identidade visual
 * imediata (mesma pessoa = mesma cor em tabela, cards e perfil).
 *
 * Tamanhos: sm (h-8, linhas de tabela), md (h-9, cards), lg (h-14, header
 * do perfil — combine com ring via className).
 */
import { cn } from "@/lib/utils";
import { hashColor } from "@/lib/color-hash";

/*
 * SAFELIST Tailwind — NÃO REMOVER.
 * O `content` do tailwind.config.ts não varre lib/, então as classes da
 * paleta de lib/color-hash.ts precisam aparecer literalmente num arquivo
 * varrido (o extractor do JIT lê comentários). Espelhe qualquer mudança lá:
 * bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/25
 * bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/25
 * bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/25
 * bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/25
 * bg-violet-500/15 text-violet-600 dark:text-violet-400 border-violet-500/25
 * bg-teal-500/15 text-teal-600 dark:text-teal-400 border-teal-500/25
 * bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/25
 * bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-400 border-fuchsia-500/25
 */

const SIZES = {
  sm: "h-8 w-8 text-[11px]",
  md: "h-9 w-9 text-xs",
  lg: "h-14 w-14 text-lg",
} as const;

/** Primeira letra do primeiro + último nome ("Maria da Silva" → "MS"). */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0].charAt(0);
  const last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : "";
  return (first + last).toUpperCase() || "?";
}

type Props = {
  name: string;
  size?: keyof typeof SIZES;
  className?: string;
};

export function ContactAvatar({ name, size = "md", className }: Props) {
  const c = hashColor(name);
  return (
    <span
      // Decorativo: o nome sempre aparece em texto ao lado do avatar.
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold",
        SIZES[size],
        c.bg,
        c.text,
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
