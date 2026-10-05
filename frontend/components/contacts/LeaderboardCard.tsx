"use client";

/**
 * LeaderboardCard — "Top lideranças · cadastros" no dashboard.
 *
 * Gamificação: ranking dos usuários que mais cadastraram contatos ativos
 * (GET /v1/contacts/leaderboard, top 10). Usa as mesmas barras de força
 * (VoteBar) dos rankings de votos. Só renderiza se houver dados.
 */
import { Trophy } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { ContactLeaderboardEntry } from "@/lib/types";
import { VoteBar } from "@/components/ui/VoteBar";

const numberFmt = new Intl.NumberFormat("pt-BR");

export function LeaderboardCard() {
  const [items, setItems] = useState<ContactLeaderboardEntry[] | null>(null);

  useEffect(() => {
    api<ContactLeaderboardEntry[]>("/v1/contacts/leaderboard")
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  // Vazio (nenhum contato com autor) ou erro: não polui o dashboard.
  if (!items || items.length === 0) return null;

  const max = items[0]?.count ?? 1;

  return (
    <div className="rounded-xl border bg-card p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Trophy className="h-4 w-4 text-amber-500" />
          Top lideranças · cadastros
        </div>
        <Link
          href="/dashboard/contacts"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Ver contatos
        </Link>
      </div>

      <ol className="space-y-3">
        {items.map((entry, i) => (
          <li key={entry.user_id}>
            <div className="flex items-baseline justify-between gap-3 mb-1">
              <p className="text-sm min-w-0 truncate">
                <span className="inline-block w-6 text-xs font-semibold text-muted-foreground tabular-nums">
                  {i + 1}º
                </span>
                {entry.full_name}
              </p>
              <span className="text-sm font-semibold tabular-nums shrink-0">
                {numberFmt.format(entry.count)}
              </span>
            </div>
            <VoteBar value={entry.count} max={max} rank={i + 1} />
          </li>
        ))}
      </ol>
    </div>
  );
}
