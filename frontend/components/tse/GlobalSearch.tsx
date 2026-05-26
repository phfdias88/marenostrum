"use client";

/**
 * Busca global no header — acha candidato, município OU partido de qualquer página.
 * - debounce 300ms
 * - chama /tse/candidates?search= e /tse/municipalities?search= em paralelo
 * - partidos: lista (~29) carregada 1x e filtrada no cliente
 * - dropdown com resultados; clique navega pra página dedicada
 * - Esc fecha, clique fora fecha
 */
import { Building2, Loader2, MapPin, Search, User, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { Page, TseCandidate, TseMunicipality, TseParty } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { StateFlag } from "@/components/tse/StateFlag";

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const debounced = useDebounce(q, 300);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [cands, setCands] = useState<TseCandidate[]>([]);
  const [munis, setMunis] = useState<TseMunicipality[]>([]);
  const [allParties, setAllParties] = useState<TseParty[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);

  // Fecha ao clicar fora
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Lista de partidos (pequena) carregada uma vez, filtrada no cliente
  useEffect(() => {
    api<TseParty[]>("/v1/tse/parties").then(setAllParties).catch(() => {});
  }, []);

  const parties = useMemo(() => {
    const t = debounced.trim().toLowerCase();
    if (t.length < 2) return [];
    return allParties
      .filter(
        (p) =>
          p.abbreviation.toLowerCase().includes(t) ||
          p.name.toLowerCase().includes(t) ||
          String(p.number) === t,
      )
      .slice(0, 4);
  }, [allParties, debounced]);

  useEffect(() => {
    const term = debounced.trim();
    if (term.length < 2) {
      setCands([]);
      setMunis([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const enc = encodeURIComponent(term);
    Promise.allSettled([
      api<Page<TseCandidate>>(`/v1/tse/candidates?search=${enc}&limit=6`),
      api<Page<TseMunicipality>>(`/v1/tse/municipalities?search=${enc}&limit=5`),
    ])
      .then(([c, m]) => {
        setCands(c.status === "fulfilled" ? c.value.items : []);
        setMunis(m.status === "fulfilled" ? m.value.items : []);
      })
      .finally(() => setLoading(false));
  }, [debounced]);

  function go(href: string) {
    setOpen(false);
    setQ("");
    router.push(href);
  }

  const hasResults = cands.length > 0 || munis.length > 0 || parties.length > 0;

  return (
    <div ref={boxRef} className="relative w-full max-w-md">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        placeholder="Buscar candidato, município ou partido…"
        className="w-full pl-9 pr-9 py-2 rounded-md bg-background border border-border text-sm
                   focus:outline-none focus:ring-2 focus:ring-primary/30"
      />
      {q && (
        <button
          onClick={() => {
            setQ("");
            setOpen(false);
          }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          aria-label="Limpar"
        >
          <X className="w-4 h-4" />
        </button>
      )}

      {open && debounced.trim().length >= 2 && (
        <div className="absolute top-full mt-2 left-0 right-0 rounded-lg border bg-card shadow-xl z-50 overflow-hidden">
          {loading ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin inline" /> buscando…
            </div>
          ) : !hasResults ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Nada encontrado para “{debounced.trim()}”.
            </div>
          ) : (
            <div className="max-h-[60vh] overflow-auto divide-y divide-border">
              {cands.length > 0 && (
                <div>
                  <p className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                    <User className="w-3 h-3" /> Candidatos
                  </p>
                  {cands.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => go(`/dashboard/analises/candidato/${c.id}`)}
                      className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-accent/50 transition-colors"
                    >
                      <CandidatePhoto
                        candidateId={c.id}
                        name={c.urn_name}
                        partyNumber={c.party.number}
                        size="sm"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{c.urn_name}</p>
                        <p className="text-xs text-muted-foreground truncate">
                          {c.party.abbreviation} · {c.office_name} · {c.state}
                        </p>
                      </div>
                      <span className="text-primary font-mono text-xs shrink-0">
                        {c.number}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {parties.length > 0 && (
                <div>
                  <p className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                    <Building2 className="w-3 h-3" /> Partidos
                  </p>
                  {parties.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => go(`/dashboard/analises/partido/${p.number}`)}
                      className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-accent/50 transition-colors"
                    >
                      <PartyLogo number={p.number} abbreviation={p.abbreviation} size="sm" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{p.abbreviation}</p>
                        <p className="text-xs text-muted-foreground truncate">{p.name}</p>
                      </div>
                      <span className="text-primary font-mono text-xs shrink-0">
                        {p.number}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {munis.length > 0 && (
                <div>
                  <p className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                    <MapPin className="w-3 h-3" /> Municípios
                  </p>
                  {munis.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => go("/dashboard/analises/municipios")}
                      className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-accent/50 transition-colors"
                    >
                      <StateFlag uf={m.state} size="sm" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{m.name}</p>
                        <p className="text-xs text-muted-foreground">{m.state}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
