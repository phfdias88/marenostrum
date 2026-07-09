"use client";

/**
 * Busca global no header — acha candidato, município, partido, CONTATO da
 * campanha ou PÁGINA do app de qualquer tela.
 * - debounce 300ms
 * - chama /tse/candidates, /tse/municipalities, /census/search-areas e
 *   /contacts (search=) em paralelo
 * - partidos: lista (~29) carregada 1x e filtrada no cliente
 * - "Páginas": lista estática das features filtrada sem acento (≥2 chars)
 * - zero-state: "Recentes" — últimas 5 seleções salvas em localStorage
 * - dropdown com resultados; clique navega pra página dedicada
 * - Esc fecha, clique fora fecha
 */
import {
  ArrowLeft,
  BarChart3,
  Building2,
  CalendarClock,
  ClipboardList,
  Compass,
  GitCompareArrows,
  History,
  Landmark,
  Layers,
  LayoutDashboard,
  LineChart,
  Loader2,
  Map,
  MapPin,
  MapPinned,
  Search,
  Settings,
  Trophy,
  User,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api";
import {
  CONTACT_TYPE_LABELS,
  type Contact,
  type Page,
  type TseCandidate,
  type TseMunicipality,
  type TseParty,
} from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { StateFlag } from "@/components/tse/StateFlag";

// Bairro/distrito do módulo Censo — backend devolve [] se o usuário
// não tem o módulo liberado, então a seção simplesmente não aparece.
type CensusArea = { cd_mun: string; nm_mun: string; nome: string; kind: string; uf: string };

// ------------------------------------------------------------- Páginas do app
// Lista estática filtrada no cliente (match sem acento). Só rotas visíveis
// por padrão pra todo usuário do dashboard: as áreas com flag do owner são
// default-ON (o guard do layout redireciona no caso raro de estarem
// desligadas). Censo fica FORA porque é módulo default-OFF e este componente
// não tem acesso ao flag — a descoberta do censo segue pela busca de bairros,
// que o backend já gateia.
type PageLink = { label: string; href: string; icon: LucideIcon; keywords?: string };

const PAGES: PageLink[] = [
  { label: "Visão geral", href: "/dashboard", icon: LayoutDashboard, keywords: "inicio home painel principal" },
  { label: "Painel", href: "/dashboard/analytics", icon: LineChart, keywords: "relatorios analytics indicadores kpi" },
  { label: "Análises", href: "/dashboard/analises", icon: BarChart3, keywords: "tse eleitoral" },
  { label: "Candidatos", href: "/dashboard/analises/candidato", icon: User, keywords: "candidato busca" },
  { label: "Partidos", href: "/dashboard/analises/partidos", icon: Building2, keywords: "partido sigla" },
  { label: "Municípios", href: "/dashboard/analises/municipios", icon: MapPin, keywords: "municipio cidade" },
  { label: "Eleições", href: "/dashboard/analises/eleicoes", icon: Landmark, keywords: "eleicao pleito turno" },
  { label: "Comparar candidatos", href: "/dashboard/analises/comparar", icon: GitCompareArrows, keywords: "comparacao versus" },
  { label: "Comparar municípios", href: "/dashboard/analises/comparar-municipios", icon: GitCompareArrows, keywords: "comparacao cidade" },
  { label: "Comparar partidos", href: "/dashboard/analises/comparar-partidos", icon: GitCompareArrows, keywords: "comparacao sigla" },
  { label: "Ranking", href: "/dashboard/analises/ranking", icon: Trophy, keywords: "mais votados top" },
  { label: "Mapa partidário", href: "/dashboard/analises/mapa", icon: Map, keywords: "mapa eleitoral vencedores" },
  { label: "Bairros", href: "/dashboard/analises/bairros", icon: Layers, keywords: "bairro voto local" },
  { label: "Zonas eleitorais", href: "/dashboard/analises/zona", icon: MapPin, keywords: "zona secao" },
  { label: "Adversários", href: "/dashboard/analises/adversarios", icon: Users, keywords: "concorrentes oponentes" },
  { label: "Projeção", href: "/dashboard/analises/projecao", icon: LineChart, keywords: "cenario simulacao" },
  { label: "Contatos", href: "/dashboard/contacts", icon: Users, keywords: "eleitores apoiadores base" },
  { label: "Demandas", href: "/dashboard/demandas", icon: ClipboardList, keywords: "pedidos solicitacoes" },
  { label: "Agenda", href: "/dashboard/agenda", icon: CalendarClock, keywords: "eventos compromissos calendario" },
  { label: "Mapa da Campanha", href: "/dashboard/map", icon: MapPinned, keywords: "territorio contatos demandas" },
  { label: "Equipe", href: "/dashboard/configuracoes", icon: Users, keywords: "membros papeis convite time" },
  { label: "Configurações", href: "/dashboard/configuracoes", icon: Settings, keywords: "conta campanha ajustes" },
];

/** Remove acentos + lowercase pra match tolerante ("analise" acha "Análises"). */
function norm(s: string): string {
  // NFD separa a letra do acento; tiramos os combining marks (U+0300-U+036F)
  // por codepoint pra nao depender de regex com caracteres literais.
  let out = "";
  for (const ch of s.normalize("NFD")) {
    const cp = ch.codePointAt(0) ?? 0;
    if (cp < 0x300 || cp > 0x36f) out += ch;
  }
  return out.toLowerCase();
}

// ---------------------------------------------------------------- Recentes
// Últimas seleções da própria busca, salvas em localStorage. Zero-state
// (query < 2 chars) mostra elas em vez do texto "digite ao menos 2 letras".
type RecentItem = { label: string; href: string; sub?: string };

const RECENT_KEY = "mn_search_recent";
const RECENT_MAX = 5;

function readRecents(): RecentItem[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const arr: unknown = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr
      .filter(
        (r): r is RecentItem =>
          !!r &&
          typeof (r as RecentItem).href === "string" &&
          typeof (r as RecentItem).label === "string",
      )
      .slice(0, RECENT_MAX);
  } catch {
    return [];
  }
}

function pushRecent(item: RecentItem) {
  try {
    const next = [item, ...readRecents().filter((r) => r.href !== item.href)].slice(0, RECENT_MAX);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // localStorage cheio/bloqueado — recentes é nice-to-have, segue sem.
  }
}

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
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [allParties, setAllParties] = useState<TseParty[]>([]);
  const [recents, setRecents] = useState<RecentItem[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const mobileInputRef = useRef<HTMLInputElement>(null);
  // Portal só monta no cliente (precisa de document). Sem isso, o overlay
  // fica preso no containing block do <header> (will-change:transform) e
  // aparece quebrado/clipado no mobile — o "não funciona no mobile" do PO.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Fecha ao clicar fora — so no desktop. Mobile fullscreen fecha por botao.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      const t = e.target as Node;
      // O overlay mobile agora vive num portal FORA do boxRef — ignora cliques
      // dentro dele também, senão fecharia a cada toque no mobile.
      const inBox = boxRef.current?.contains(t);
      const inOverlay = overlayRef.current?.contains(t);
      if (!inBox && !inOverlay) setOpen(false);
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

  // Recentes: relê do localStorage sempre que a busca abre (outra aba ou
  // outra instância do componente pode ter gravado nesse meio-tempo).
  useEffect(() => {
    if (open) setRecents(readRecents());
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

  // Páginas do app — filtro estático sem acento, aparece no topo.
  const pages = useMemo(() => {
    const t = norm(debounced.trim());
    if (t.length < 2) return [];
    return PAGES.filter(
      (p) => norm(p.label).includes(t) || (p.keywords ? norm(p.keywords).includes(t) : false),
    ).slice(0, 5);
  }, [debounced]);

  useEffect(() => {
    const term = debounced.trim();
    if (term.length < 2) {
      setCands([]);
      setMunis([]);
      setAreas([]);
      setContacts([]);
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
      api<Page<Contact>>(`/v1/contacts?search=${enc}&limit=5`),
    ])
      .then(([c, m, a, ct]) => {
        if (!active) return;
        setCands(c.status === "fulfilled" ? c.value.items : []);
        setMunis(m.status === "fulfilled" ? m.value.items : []);
        setAreas(a.status === "fulfilled" ? a.value : []);
        setContacts(ct.status === "fulfilled" ? ct.value.items : []);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [debounced]);

  function go(href: string, recent?: { label: string; sub?: string }) {
    if (recent) {
      pushRecent({ href, label: recent.label, sub: recent.sub });
      setRecents(readRecents());
    }
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
    pages.length > 0 ||
    contacts.length > 0 ||
    cands.length > 0 ||
    munis.length > 0 ||
    parties.length > 0 ||
    areas.length > 0;

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
        placeholder="Buscar candidato, contato, município…"
        // text-base no mobile (≥16px) evita o zoom automático do iOS Safari ao
        // focar; text-sm só no desktop.
        className="w-full pl-9 pr-9 py-2 rounded-md bg-background border border-border text-base md:text-sm
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

      {/* === MOBILE FULL-SCREEN OVERLAY (portal p/ escapar o header, que tem
          will-change:transform e aprisionaria o position:fixed) === */}
      {open && mounted && createPortal(
        <div
          ref={overlayRef}
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
                placeholder="Buscar candidato, contato, município…"
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
              recents.length > 0 ? (
                <RecentList recents={recents} onGo={go} mobile />
              ) : (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  Digite ao menos 2 letras pra buscar candidatos, contatos, municípios,
                  partidos ou páginas do app.
                </div>
              )
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
                pages={pages}
                contacts={contacts}
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
        </div>,
        document.body,
      )}

      {/* === DESKTOP DROPDOWN === */}
      {open && (debounced.trim().length >= 2 || recents.length > 0) && (
        <div className="hidden md:block absolute top-full mt-2 left-0 right-0 rounded-lg border bg-card shadow-xl z-50 overflow-hidden">
          {debounced.trim().length < 2 ? (
            <RecentList recents={recents} onGo={go} />
          ) : loading ? (
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
                pages={pages}
                contacts={contacts}
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

// ------------------------------------------- Recentes (zero-state da busca)

function RecentList({
  recents,
  onGo,
  mobile = false,
}: {
  recents: RecentItem[];
  onGo: (href: string, recent?: { label: string; sub?: string }) => void;
  mobile?: boolean;
}) {
  const itemCls = mobile
    ? "w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-accent/50 transition-colors min-h-[56px]"
    : "w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-accent/50 transition-colors";
  const sectCls = mobile
    ? "px-4 pt-3 pb-1 text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5"
    : "px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1";

  return (
    <div>
      <p className={sectCls}>
        <History className={mobile ? "w-3.5 h-3.5" : "w-3 h-3"} /> Recentes
      </p>
      {recents.map((r) => (
        <button
          key={r.href}
          onClick={() => onGo(r.href, { label: r.label, sub: r.sub })}
          className={itemCls}
        >
          <span className="grid place-items-center w-8 h-8 rounded-md bg-accent/60 text-muted-foreground shrink-0">
            <History className="w-4 h-4" />
          </span>
          <div className="flex-1 min-w-0">
            <p className={mobile ? "text-base font-medium truncate" : "text-sm font-medium truncate"}>
              {r.label}
            </p>
            {r.sub && (
              <p className={mobile ? "text-sm text-muted-foreground truncate" : "text-xs text-muted-foreground truncate"}>
                {r.sub}
              </p>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------- Result list reusavel (desktop + mobile)

function ResultList({
  pages,
  contacts,
  cands,
  parties,
  munis,
  areas,
  onGo,
  router,
  mobile = false,
}: {
  pages: PageLink[];
  contacts: Contact[];
  cands: TseCandidate[];
  parties: TseParty[];
  munis: TseMunicipality[];
  areas: CensusArea[];
  onGo: (href: string, recent?: { label: string; sub?: string }) => void;
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
      {pages.length > 0 && (
        <div>
          <p className={sectCls}>
            <Compass className={mobile ? "w-3.5 h-3.5" : "w-3 h-3"} /> Páginas
          </p>
          {pages.map((p) => (
            <button
              key={`${p.href}:${p.label}`}
              onClick={() => onGo(p.href, { label: p.label, sub: "Página" })}
              onMouseEnter={() => router.prefetch(p.href)}
              className={itemCls}
            >
              <span className="grid place-items-center w-8 h-8 rounded-md bg-primary/15 text-primary shrink-0">
                <p.icon className="w-4 h-4" />
              </span>
              <div className="flex-1 min-w-0">
                <p className={titleCls}>{p.label}</p>
              </div>
            </button>
          ))}
        </div>
      )}
      {contacts.length > 0 && (
        <div>
          <p className={sectCls}>
            <Users className={mobile ? "w-3.5 h-3.5" : "w-3 h-3"} /> Contatos
          </p>
          {contacts.map((c) => {
            const sub = [
              CONTACT_TYPE_LABELS[c.type],
              c.neighborhood,
              c.city,
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <button
                key={c.id}
                onClick={() => onGo(`/dashboard/contacts/${c.id}`, { label: c.full_name, sub })}
                onMouseEnter={() => router.prefetch(`/dashboard/contacts/${c.id}`)}
                className={itemCls}
              >
                <span className="grid place-items-center w-8 h-8 rounded-md bg-primary/15 text-primary shrink-0">
                  <Users className="w-4 h-4" />
                </span>
                <div className="flex-1 min-w-0">
                  <p className={titleCls}>{c.full_name}</p>
                  {sub && <p className={subCls}>{sub}</p>}
                </div>
              </button>
            );
          })}
        </div>
      )}
      {cands.length > 0 && (
        <div>
          <p className={sectCls}>
            <User className={mobile ? "w-3.5 h-3.5" : "w-3 h-3"} /> Candidatos
          </p>
          {cands.map((c) => (
            <button
              key={c.id}
              onClick={() =>
                onGo(`/dashboard/analises/candidato/${c.id}`, {
                  label: c.urn_name,
                  sub: `${c.party.abbreviation} · ${c.office_name} · ${c.election.year}`,
                })
              }
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
              onClick={() =>
                onGo(`/dashboard/analises/partido/${p.number}`, {
                  label: p.abbreviation,
                  sub: p.name,
                })
              }
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
                onGo(`/dashboard/censo?mun=${a.cd_mun}&area=${encodeURIComponent(a.nome)}`, {
                  label: a.nome,
                  sub: `${a.kind} · ${a.nm_mun} · ${a.uf}`,
                })
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
              onClick={() =>
                onGo(`/dashboard/analises/municipio/${m.id}`, {
                  label: m.name,
                  sub: m.state,
                })
              }
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
