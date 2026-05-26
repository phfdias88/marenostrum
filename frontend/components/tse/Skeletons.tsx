"use client";

/**
 * Skeletons reutilizáveis das telas TSE — substituem spinners "pelados"
 * por placeholders com a forma do conteúdo, reduzindo a sensação de espera.
 */
import { Skeleton } from "@/components/ui/skeleton";

/** Uma linha de candidato (foto + nome + meta + valor). */
export function CandidateRowSkeleton() {
  return (
    <div className="p-4 flex items-center gap-4">
      <Skeleton className="w-14 h-14 rounded-full shrink-0" />
      <div className="flex-1 min-w-0 space-y-2">
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="h-3 w-3/5" />
      </div>
      <Skeleton className="h-4 w-12 shrink-0" />
    </div>
  );
}

/** Lista de N linhas de candidato dentro de um card. */
export function CandidateListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="rounded-lg border bg-card divide-y divide-border">
      {Array.from({ length: rows }).map((_, i) => (
        <CandidateRowSkeleton key={i} />
      ))}
    </div>
  );
}

/** Esqueleto da página dedicada do candidato (hero + stats + lista). */
export function CandidateDetailSkeleton() {
  return (
    <div className="space-y-4">
      {/* hero */}
      <div className="rounded-xl border bg-card p-6 flex flex-col sm:flex-row items-center sm:items-start gap-5">
        <Skeleton className="w-32 h-32 rounded-full shrink-0" />
        <div className="flex-1 w-full space-y-3">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-6 w-24 rounded-full" />
        </div>
      </div>
      {/* stats */}
      <div className="grid grid-cols-2 gap-3">
        <Skeleton className="h-20 rounded-lg" />
        <Skeleton className="h-20 rounded-lg" />
      </div>
      {/* lista */}
      <Skeleton className="h-3 w-32" />
      <div className="rounded-lg border bg-card divide-y divide-border">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center justify-between px-4 py-2.5">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="h-4 w-12" />
          </div>
        ))}
      </div>
    </div>
  );
}
