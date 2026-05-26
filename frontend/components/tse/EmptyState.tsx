"use client";

/**
 * Estado vazio padronizado — ícone + título + dica.
 * Usado quando uma busca/filtro não retorna resultados.
 */
import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  hint,
  className = "",
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={`p-10 text-center ${className}`}>
      <div className="mx-auto w-12 h-12 rounded-full bg-muted grid place-items-center mb-3">
        <Icon className="w-6 h-6 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
    </div>
  );
}
