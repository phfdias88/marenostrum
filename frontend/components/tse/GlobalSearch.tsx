"use client";

/**
 * Busca global no header — acha candidato, município OU partido de qualquer página.
 * - debounce 300ms
 * - chama /tse/candidates?search= e /tse/municipalities?search= em paralelo
 * - partidos: lista (~29) carregada 1x e filtrada no cliente
 * - dropdown com resultados; clique navega pra página dedicada
 * - Esc fecha, clique fora fecha
 */
import { ArrowLeft, Building2, Layers, Loader2, MapPin, Search, User, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { Page, TseCandidate, TseMunicipality, TseParty } from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { StateFlag } from "@/components/tse/StateFlag";

// Bairro/distrito do módulo Censo — backend devolve [] se o usuário
// não tem o módulo liberado, então a seção simplesmente não aparece.
type CensusArea = { cd_mun: string; nm_mun: string; nome: string; kind: string; uf: string };

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
  const [areas, setAreas] = useState<CensusArea[]>([]);
  const [allParties, setAllParties] = useState<TseParty[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const mobileInputRef = useRef<HTMLInputElement>(null);

  // Fecha ao clicar fora — so no desktop. Mobile fullscreen fecha por botao.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Atalho global Cmd/Ctrl+K → abre + foca a busca de qualquer página.
  // Padrao consagrado (Linear, GitHub, Vercel). "/" tambem abre, exceto
  // quando ja' digitando num campo.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const cmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      const target = e.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      const slash = e.key === "/" && !typing;
      if (cmdK || slash) {
        e.preventDefault();
        setOpen(true);
        // foco no input certo conforme viewport
        setTimeout(() => {
          if (window.innerWidth < 768) mobileInputRef.current?.focus();
          else inputRef.current?.focus();
        }, 30);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Quando abre no mobile (md:hidden), trava o scroll do body
  useEffect(() => {
    if (open && typeof window !== "undefined" && window.innerWidth < 768) {
      document.body.style.overflow = "hidden";
      // Foca o input do modal pra teclado abrir direto
      setTimeout(() => mobileInputRef.current?.focus(), 50);
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

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
      setAreas([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const enc = encodeURIComponent(term);
    // Guard anti-race: resposta de um termo antigo (mais lenta) não pode
    // sobrescrever a do termo atual. Só aplica se este effect ainda é o vigente.
    let active = true;
    Promise.allSettled([
      api<Page<TseCandidate>>(`/v1/tse/candidates?search=${enc}&group_person=true&limit=6`),
      api<Page<TseMunicipality>>(`/v1/tse/municipalities?search=${enc}&limit=5`),
      api<CensusArea[]>(`/v1/census/search-areas?q=${enc}`),
    ])
      .then(([c, m, a]) => {
        if (!active) return;
        setCands(c.status === "fulfilled" ? c.value.items : []);
        setMunis(m.status === "fulfilled" ? m.value.items : []);
        setAreas(a.status === "fulfilled" ? a.value : []);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [debounced]);

  function go(href: string) {
    setOpen(false);
    setQ("");
    // Censo: a página lê ?mun=&area= só na montagem — se já estamos nela,
    // o router.push não remonta; navegação completa resolve (dados em cache).
    if (
      href.startsWith("/dashboard/censo?") &&
      window.location.pathname === "/dashboard/censo"
    ) {
      window.location.href = href;
      return;
    }
    router.push(href);
  }

  const hasResults =
    cands.length > 0 || munis.length > 0 || parties.length > 0 || areas.length > 0;

  // Renderizado em 2 modos:
  // - Desktop (md+): input inline + dropdown absoluto abaixo
  // - Mobile (<md): input no header dispara overlay full-screen com input
  //   maior + resultados em altura total
  return (
    <div ref={boxRef} className="relative w-full max-w-md">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
      <input
        ref={inputRef}
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
      {q ? (
        <button
          onClick={() => {
            setQ("");
            setOpen(false);
          }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground hidden md:inline-flex"
          aria-label="Limpar"
        >
          <X className="w-4 h-4" />
        </button>
      ) : null}

      {/* === MOBILE FULL-SCREEN OVERLAY === */}
      {open && (
        <div
          className="md:hidden fixed inset-0 z-[60] bg-background flex flex-col"
          style={{ paddingTop: "env(safe-area-inset-top)" }}
        >
          <div className="flex items-center gap-2 p-3 border-b border-border">
            <button
              onClick={() => {
                setOpen(false);
                setQ("");
              }}
              className="p-2 -ml-2 rounded-full hover:bg-accent/50"
              aria-label="Fechar busca"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
              <input
                ref={mobileInputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
                placeholder="Buscar candidato, município ou partido…"
                className="w-full pl-9 pr-9 py-3 text-base rounded-md bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
              {q && (
                <button
                  onClick={() => setQ("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label="Limpar"
                >
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-auto">
            {debounced.trim().length < 2 ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                Digite ao menos 2 letras pra buscar candidatos, municípios ou partidos.
              </div>
            ) : loading ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin inline mr-2" /> buscando…
              </div>
            ) : !hasResults ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                Nada encontrado para "{debounced.trim()}".
              </div>
            ) : (
              <ResultList
                cands={cands}
                parties={parties}
                munis={munis}
                areas={areas}
                onGo={go}
                router={router}
                mobile
              />
            )}
          </div>
        </div>
      )}

      {/* === DESKTOP DROPDOWN === */}
      {open && debounced.trim().length >= 2 && (
        <div className="hidden md:block absolute top-full mt-2 left-0 right-0 rounded-lg border bg-card shadow-xl z-50 overflow-hidden">
          {loading ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin inline" /> buscando…
            </div>
          ) : !hasResults ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Nada encontrado para "{debounced.trim()}".
            </div>
          ) : (
            <div className="max-h-[60vh] overflow-auto divide-y divide-border">
              <ResultList
                cands={cands}
                parties={parties}
                munis={munis}
                areas={areas}
                onGo={go}
                router={router}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------- Result list reusavel (desktop + mobile)

function ResultList({
  cands,
  parties,
  munis,
  areas,
  onGo,
  router,
  mobile = false,
}: {
  cands: TseCandidate[];
  parties: TseParty[];
  munis: TseMunicipality[];
  areas: CensusArea[];
  onGo: (href: string) => void;
  router: ReturnType<typeof useRouter>;
  mobile?: boolean;
}) {
  // Mobile: padding/altura maior pra touch
  const itemCls = mobile
    ? "w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-accent/50 transition-colors min-h-[56px]"
    : "w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-accent/50 transition-colors";
  const titleCls = mobile ? "text-base font-medium truncate" : "text-sm font-medium truncate";
  const subCls = mobile ? "text-sm text-muted-foreground truncate" : "text-xs text-muted-foreground truncate";
  const sectCls = mobile
    ? "px-4 pt-3 pb-1 text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5"
    : "px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1";

  return (
    <div className={mobile ? "divide-y divide-border" : ""}>
      {cands.length > 0 && (
        <div>
          <p className={sectCls}>
            <User className={mobile ? "w-3.5 h-3.5" : "w-3 h-3"} /> Candidatos
          </p>
          {cands.map((c) => (
            <button
              key={c.id}
              onClick={() => onGo(`/dashboard/analises/candidato/${c.id}`)}
              onMouseEnter={() => router.prefetch(`/dashboard/analises/candidato/${c.id}`)}
              className={itemCls}
            >
              <CandidatePhoto
                candidateId={c.id}
                name={c.urn_name}
                partyNumber={c.party.number}
                size={mobile ? "md" : "sm"}
              />
              <div className="flex-1 min-w-0">
                <p className={titleCls}>{c.urn_name}</p>
                <p className={subCls}>
                  {c.party.abbreviation} · {c.office_name} · {c.state} · {c.election.year}
                  {c.candidacy_count && c.candidacy_count > 1 ? (
                    <span className="ml-1.5 text-primary/80">· {c.candidacy_count} candidaturas</span>
                  ) : null}
                </p>
                {/* Nome civil — desambigua homônimos (vários candidatos com o
                    mesmo nome de urna são pessoas diferentes). */}
                {c.name && c.name.toLowerCase() !== c.urn_name.toLowerCase() && (
                  <p className="text-[10px] text-muted-foreground/70 truncate">
                    {c.name}
                  </p>
                )}
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
          <p className={sectCls}>
            <Building2 className={mobile ? "w-3.5 h-3.5" : "w-3 h-3"} /> Partidos
          </p>
          {parties.map((p) => (
            <button
              key={p.id}
              onClick={() => onGo(`/dashboard/analises/partido/${p.number}`)}
              onMouseEnter={() => router.prefetch(`/dashboard/analises/partido/${p.number}`)}
              className={itemCls}
            >
              <PartyLogo number={p.number} abbreviation={p.abbreviation} size={mobile ? "md" : "sm"} />
              <div className="flex-1 min-w-0">
                <p className={titleCls}>{p.abbreviation}</p>
                <p className={subCls}>{p.name}</p>
              </div>
              <span className="text-primary font-mono text-xs shrink-0">
                {p.number}
              </span>
            </button>
          ))}
        </div>
      )}
      {areas.length > 0 && (
        <div>
          <p className={sectCls}>
            <Layers className={mobile ? "w-3.5 h-3.5" : "w-3 h-3"} /> Bairros · Censo
          </p>
          {areas.map((a) => (
            <button
              key={`${a.cd_mun}:${a.nome}`}
              onClick={() =>
                onGo(`/dashboard/censo?mun=${a.cd_mun}&area=${encodeURIComponent(a.nome)}`)
              }
              onMouseEnter={() => router.prefetch("/dashboard/censo")}
              className={itemCls}
            >
              <span className="grid place-items-center w-8 h-8 rounded-md bg-primary/15 text-primary shrink-0">
                <Layers className="w-4 h-4" />
              </span>
              <div className="flex-1 min-w-0">
                <p className={titleCls}>{a.nome}</p>
                <p className={subCls}>
                  {a.kind} · {a.nm_mun} · {a.uf}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}
      {munis.length > 0 && (
        <div>
          <p className={sectCls}>
            <MapPin className={mobile ? "w-3.5 h-3.5" : "w-3 h-3"} /> Municípios
          </p>
          {munis.map((m) => (
            <button
              key={m.id}
              onClick={() => onGo(`/dashboard/analises/municipio/${m.id}`)}
              onMouseEnter={() => router.prefetch(`/dashboard/analises/municipio/${m.id}`)}
              className={itemCls}
            >
              <StateFlag uf={m.state} size={mobile ? "md" : "sm"} />
              <div className="flex-1 min-w-0">
                <p className={titleCls}>{m.name}</p>
                <p className={mobile ? "text-sm text-muted-foreground" : "text-xs text-muted-foreground"}>{m.state}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
