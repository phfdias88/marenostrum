"use client";

/**
 * Modal fullscreen com mapa de votacao de um candidato.
 *
 * Recebe TseCandidateResults ja carregado (resultado de /candidates/{id}/results)
 * pra evitar refetch.
 */
import { X } from "lucide-react";
import dynamic from "next/dynamic";

import type { TseCandidateResults } from "@/lib/types";

const CandidateVoteMap = dynamic(
  () => import("@/components/map/CandidateVoteMap"),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full grid place-items-center text-muted-foreground">
        Carregando mapa…
      </div>
    ),
  },
);

const numberFmt = new Intl.NumberFormat("pt-BR");

type Props = {
  results: TseCandidateResults;
  onClose: () => void;
};

export function CandidateMapModal({ results, onClose }: Props) {
  const c = results.candidate;

  return (
    <div className="fixed inset-0 bg-black/70 z-50 grid place-items-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden">
        <header className="flex items-center justify-between p-4 border-b border-border">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Distribuição de votos · {c.office_name} · {c.state}
            </p>
            <h2 className="text-lg font-bold truncate">
              {c.urn_name}{" "}
              <span className="text-primary font-mono ml-2">{c.number}</span>{" "}
              <span className="text-muted-foreground text-sm font-normal">
                {c.party.abbreviation}
              </span>
            </h2>
            <p className="text-xs text-muted-foreground mt-1">
              <strong className="text-foreground">
                {numberFmt.format(results.total_votes)}
              </strong>{" "}
              votos em{" "}
              <strong className="text-foreground">
                {numberFmt.format(results.municipalities_with_votes)}
              </strong>{" "}
              município(s)
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground p-2 hover:bg-accent rounded-md"
            aria-label="Fechar"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="flex-1 min-h-0">
          <CandidateVoteMap results={results} />
        </div>
      </div>
    </div>
  );
}
