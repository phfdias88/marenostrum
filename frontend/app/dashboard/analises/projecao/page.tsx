"use client";

/**
 * Projeção Eleitoral — Quociente Eleitoral + D'Hondt.
 *
 * Calcula, com base no resultado historico de uma cidade num cargo
 * proporcional (Vereador, Deputado Federal, Estadual, Distrital):
 *  - Quociente Eleitoral (QE) = votos validos / cadeiras
 *  - Cláusula de barreira: partido precisa atingir QE pra eleger 1 cadeira
 *    (Lei 9.504/97, alterada por 13.165/2015)
 *  - D'Hondt (maiores médias) pra distribuir sobras
 *  - Lei 14.211/2021: candidato individual precisa atingir 10% do QE
 *    pra ser elegivel pelo partido
 *
 * Modo "e se": ajuste de votos por partido pra simular cenarios.
 */
import { ArrowLeft, Calculator, Crown, Download, Info, RotateCcw, Search, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";
import type {
  Page,
  TseMunicipality,
  TseMunicipalityResults,
} from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { PartyLogo } from "@/components/tse/PartyLogo";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";

const numberFmt = new Intl.NumberFormat("pt-BR");
const pctFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

// Cargos proporcionais — eleitos via QE + D'Hondt (nao majoritarios)
const OFFICES: { code: string; label: string; year: string }[] = [
  { code: "13", label: "Vereador (2024)", year: "2024" },
  { code: "6", label: "Deputado Federal (2022)", year: "2022" },
  { code: "7", label: "Deputado Estadual (2022)", year: "2022" },
  { code: "8", label: "Deputado Distrital (2022)", year: "2022" },
];

// Estimativa default de cadeiras pra cargo (usuario pode ajustar manual)
// Constituição Art. 29: vereador varia por populacao (9 a 55).
// Dep Federal/Estadual: por estado.
const DEFAULT_SEATS: Record<string, number> = {
  "13": 13,    // vereador medio
  "6": 8,      // dep federal min por estado
  "7": 24,     // dep estadual min por estado
  "8": 24,     // dep distrital DF
};

// -------------------------------- D'Hondt
type PartyAgg = {
  party_number: number;
  party_abbr: string;
  party_name: string;
  candidates: {
    id: string;
    urn_name: string;
    name: string;
    votes: number;
    photo_id: string;
    result_status: string | null;
  }[];
  total_votes: number;
};

type DHondtResult = {
  party: PartyAgg;
  seats: number;
  meanLast: number; // ultima media usada
  passedBarrier: boolean;
};

/**
 * Aplica D'Hondt: as primeiras N maiores "medias" votos/divisor recebem
 * cada uma 1 cadeira. Divisor cresce conforme o partido ganha cadeiras.
 * Cláusula de barreira: descarta partidos abaixo do QE antes do D'Hondt.
 */
function applyDHondt(parties: PartyAgg[], seats: number, qe: number): DHondtResult[] {
  // Cláusula de barreira (Lei 13.165/2015)
  const eligible = parties.map((p) => ({
    party: p,
    seats: 0,
    meanLast: 0,
    passedBarrier: p.total_votes >= qe,
  }));
  const competing = eligible.filter((e) => e.passedBarrier);

  // Iteracoes D'Hondt
  for (let i = 0; i < seats; i++) {
    // Calcula media de cada partido competidor
    let bestIdx = -1;
    let bestMean = -1;
    for (let j = 0; j < competing.length; j++) {
      const c = competing[j];
      const mean = c.party.total_votes / (c.seats + 1);
      if (mean > bestMean) {
        bestMean = mean;
        bestIdx = j;
      }
    }
    if (bestIdx === -1) break; // sem partidos elegiveis
    competing[bestIdx].seats++;
    competing[bestIdx].meanLast = bestMean;
  }

  return eligible;
}

export default function ProjecaoPage() {
  const [office, setOffice] = useState<string>("13");
  const [year, setYear] = useState<string>("2024");
  const [seats, setSeats] = useState<number>(13);

  // Busca cidade
  const [muniSearch, setMuniSearch] = useState("");
  const muniDebounced = useDebounce(muniSearch, 300);
  const [muniResults, setMuniResults] = useState<TseMunicipality[]>([]);
  const [selectedMuni, setSelectedMuni] = useState<TseMunicipality | null>(null);
  const [state, setState] = useState("MG");

  // Dados
  const [results, setResults] = useState<TseMunicipalityResults | null>(null);
  const [loading, setLoading] = useState(false);

  // Edicoes "e se" — map party_number -> override de votos
  const [overrides, setOverrides] = useState<Record<number, number>>({});

  // Quando muda cargo, atualiza year e seats default
  useEffect(() => {
    const opt = OFFICES.find((o) => o.code === office);
    if (opt) setYear(opt.year);
    setSeats(DEFAULT_SEATS[office] ?? 13);
    setOverrides({});
  }, [office]);

  // Busca cidades conforme digita
  useEffect(() => {
    if (selectedMuni) return;
    const q = muniDebounced.trim();
    if (q.length < 2) { setMuniResults([]); return; }
    const p = new URLSearchParams({ limit: "10", search: q });
    if (state) p.set("state", state);
    api<Page<TseMunicipality>>(`/v1/tse/municipalities?${p.toString()}`)
      .then((r) => setMuniResults(r.items))
      .catch(() => setMuniResults([]));
  }, [muniDebounced, state, selectedMuni]);

  // Carrega top candidatos quando cidade + cargo + ano definidos
  useEffect(() => {
    if (!selectedMuni) { setResults(null); return; }
    setLoading(true);
    setOverrides({});
    const p = new URLSearchParams({ limit: "500", year, office_code: office });
    api<TseMunicipalityResults>(
      `/v1/tse/municipalities/${selectedMuni.id}/top-candidates?${p.toString()}`,
    )
      .then(setResults)
      .catch(() => setResults(null))
      .finally(() => setLoading(false));
  }, [selectedMuni, office, year]);

  // Agrega por partido + aplica overrides
  const parties: PartyAgg[] = useMemo(() => {
    if (!results) return [];
    const map = new Map<number, PartyAgg>();
    for (const r of results.results) {
      const pn = r.candidate.party.number;
      const slot = map.get(pn) ?? {
        party_number: pn,
        party_abbr: r.candidate.party.abbreviation,
        party_name: r.candidate.party.name,
        candidates: [],
        total_votes: 0,
      };
      slot.candidates.push({
        id: r.candidate.id,
        urn_name: r.candidate.urn_name,
        name: r.candidate.name,
        votes: r.votes,
        photo_id: r.candidate.id,
        result_status: r.candidate.result_status,
      });
      slot.total_votes += r.votes;
      map.set(pn, slot);
    }
    // Aplica overrides — substitui o total do partido por valor manual
    const arr = Array.from(map.values()).map((p) => {
      const ov = overrides[p.party_number];
      if (ov !== undefined) {
        // Escala votos individuais proporcionalmente
        const factor = p.total_votes > 0 ? ov / p.total_votes : 0;
        return {
          ...p,
          total_votes: ov,
          candidates: p.candidates.map((c) => ({ ...c, votes: Math.round(c.votes * factor) })),
        };
      }
      return p;
    });
    return arr.sort((a, b) => b.total_votes - a.total_votes);
  }, [results, overrides]);

  // QE = total / cadeiras
  const totalValidos = parties.reduce((s, p) => s + p.total_votes, 0);
  const qe = seats > 0 ? Math.floor(totalValidos / seats) : 0;
  const dhondt = useMemo(() => applyDHondt(parties, seats, qe), [parties, seats, qe]);
  const totalElectedByDhondt = dhondt.reduce((s, d) => s + d.seats, 0);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 sm:py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-6 flex items-center gap-3">
        <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
          <Calculator className="w-5 h-5" />
        </span>
        <div>
          <h1 className="text-2xl font-bold">Projeção Eleitoral</h1>
          <p className="text-sm text-muted-foreground">
            Quociente Eleitoral + D'Hondt aplicado ao resultado histórico TSE.
          </p>
        </div>
      </header>

      {/* Filtros */}
      <section className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-6">
        <div className="md:col-span-3">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">Cargo (proporcional)</label>
          <select
            value={office}
            onChange={(e) => setOffice(e.target.value)}
            className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            {OFFICES.map((o) => (
              <option key={o.code} value={o.code}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">Cadeiras</label>
          <input
            type="number"
            min={1}
            max={100}
            value={seats}
            onChange={(e) => setSeats(Math.max(1, parseInt(e.target.value) || 1))}
            className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div className="md:col-span-2">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">UF</label>
          <select
            value={state}
            onChange={(e) => { setState(e.target.value); setSelectedMuni(null); setMuniSearch(""); }}
            className="w-full mt-1 py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            {["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"].map((u) => (
              <option key={u} value={u}>{u}</option>
            ))}
          </select>
        </div>
        <div className="md:col-span-5">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">Cidade</label>
          {selectedMuni ? (
            <div className="mt-1 flex items-center justify-between gap-2 py-2 px-3 rounded-md bg-card border border-primary/40">
              <span className="font-semibold truncate">
                {selectedMuni.name}<span className="text-muted-foreground font-normal">/{selectedMuni.state}</span>
              </span>
              <button onClick={() => { setSelectedMuni(null); setMuniSearch(""); }} aria-label="Trocar cidade">
                <X className="w-4 h-4 text-muted-foreground hover:text-foreground" />
              </button>
            </div>
          ) : (
            <div className="relative mt-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={muniSearch}
                onChange={(e) => setMuniSearch(e.target.value)}
                placeholder="Buscar cidade…"
                className="w-full pl-9 py-2 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          )}
        </div>
      </section>

      {/* Dropdown cidades */}
      {!selectedMuni && muniResults.length > 0 && (
        <div className="rounded-lg border bg-card divide-y divide-border mb-6 max-h-60 overflow-auto">
          {muniResults.map((m) => (
            <button
              key={m.id}
              onClick={() => { setSelectedMuni(m); setMuniResults([]); }}
              className="w-full text-left p-3 hover:bg-accent/50 transition-colors flex items-center justify-between"
            >
              <span className="font-medium">{m.name}</span>
              <span className="text-xs text-muted-foreground">{m.state}</span>
            </button>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!selectedMuni && (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
          <Calculator className="mx-auto h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground mt-3">
            Escolha cidade + cargo proporcional pra calcular o quociente eleitoral e ver quem elege na próxima eleição (D'Hondt).
          </p>
        </div>
      )}

      {/* Loading */}
      {selectedMuni && loading && (
        <div className="py-16 text-center text-muted-foreground">Carregando dados…</div>
      )}

      {/* Resultado */}
      {selectedMuni && !loading && results && (
        <>
          {/* Toolbar com exportar */}
          <div className="flex items-center justify-end mb-3">
            <button
              onClick={() => {
                const minimo = Math.ceil(qe * 0.1);
                const rows: Record<string, unknown>[] = [];
                dhondt.forEach((d) => {
                  const elegiveis = d.party.candidates
                    .filter((c) => c.votes >= minimo)
                    .sort((a, b) => b.votes - a.votes);
                  const eleitos = elegiveis.slice(0, d.seats);
                  eleitos.forEach((c, idx) => {
                    rows.push({
                      partido: d.party.party_abbr,
                      partido_votos: d.party.total_votes,
                      partido_cadeiras: d.seats,
                      partido_passou_barreira: d.passedBarrier ? "Sim" : "Não",
                      ordem_no_partido: idx + 1,
                      candidato: c.urn_name,
                      nome: c.name,
                      votos: c.votes,
                      pct_qe: ((c.votes / qe) * 100).toFixed(1).replace(".", ","),
                      situacao_original: c.result_status ?? "",
                      eleito_projecao: "Sim",
                    });
                  });
                });
                downloadCsv(
                  `projecao-${selectedMuni.name}-${OFFICES.find((o) => o.code === office)?.label.replace(/[^a-zA-Z0-9]+/g, "-")}-${year}`.toLowerCase(),
                  [
                    { key: "partido", label: "Partido" },
                    { key: "partido_votos", label: "Votos do partido" },
                    { key: "partido_cadeiras", label: "Cadeiras (D'Hondt)" },
                    { key: "partido_passou_barreira", label: "Passou barreira" },
                    { key: "ordem_no_partido", label: "Ordem interna" },
                    { key: "candidato", label: "Candidato" },
                    { key: "nome", label: "Nome civil" },
                    { key: "votos", label: "Votos" },
                    { key: "pct_qe", label: "% do QE" },
                    { key: "situacao_original", label: "Situação real TSE" },
                    { key: "eleito_projecao", label: "Eleito (projeção)" },
                  ],
                  rows,
                );
              }}
              disabled={!results || totalValidos === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border bg-card text-sm hover:border-primary/60 transition-colors disabled:opacity-50"
              aria-label="Exportar projecao em CSV"
              title="Exportar projeção CSV"
            >
              <Download className="w-4 h-4" />
              <span className="hidden sm:inline">Exportar CSV</span>
            </button>
          </div>

          {/* QE + stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard label="Votos válidos" value={totalValidos} tone="muted" />
            <StatCard label="Cadeiras" value={seats} tone="muted" />
            <StatCard label="Quociente eleitoral (QE)" value={qe} tone="primary" />
            <StatCard label="Partidos com barreira" value={dhondt.filter((d) => d.passedBarrier).length} tone="emerald" />
          </div>

          {/* Tabela D'Hondt — partidos */}
          <section className="rounded-xl border bg-card mb-6">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <div>
                <h2 className="font-bold">Distribuição de cadeiras por partido (D'Hondt)</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {totalElectedByDhondt} de {seats} cadeiras alocadas
                  {Object.keys(overrides).length > 0 && (
                    <span className="text-amber-400 ml-2">· cenário editado</span>
                  )}
                </p>
              </div>
              {Object.keys(overrides).length > 0 && (
                <button
                  onClick={() => setOverrides({})}
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:border-primary/60 transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Reset
                </button>
              )}
            </div>
            <ul className="divide-y divide-border">
              {dhondt.map((d, i) => (
                <PartyRow
                  key={d.party.party_number}
                  rank={i + 1}
                  d={d}
                  qe={qe}
                  totalSeats={seats}
                  override={overrides[d.party.party_number]}
                  onOverride={(v) => {
                    setOverrides((o) => ({ ...o, [d.party.party_number]: v }));
                  }}
                  onClearOverride={() => {
                    setOverrides((o) => {
                      const n = { ...o };
                      delete n[d.party.party_number];
                      return n;
                    });
                  }}
                />
              ))}
            </ul>
          </section>

          {/* Alocacao individual: candidatos eleitos por partido */}
          <section className="rounded-xl border bg-card mb-6">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="font-bold">Candidatos eleitos (puxadores + sobras)</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Dentro do partido, eleitos sao os com mais votos individuais. Lei 14.211/2021:
                candidato precisa atingir <strong>10% do QE</strong> ({numberFmt.format(Math.ceil(qe * 0.1))} votos) pra ser elegivel.
              </p>
            </div>
            <ul className="divide-y divide-border">
              {dhondt
                .filter((d) => d.seats > 0)
                .map((d) => {
                  const minimo = Math.ceil(qe * 0.1);
                  const elegiveis = d.party.candidates
                    .filter((c) => c.votes >= minimo)
                    .sort((a, b) => b.votes - a.votes);
                  const eleitos = elegiveis.slice(0, d.seats);
                  return (
                    <li key={d.party.party_number} className="p-3 sm:p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <PartyLogo number={d.party.party_number} abbreviation={d.party.party_abbr} size="sm" />
                        <div className="flex-1 min-w-0">
                          <p className="font-bold truncate">
                            {d.party.party_abbr}
                            <span className="text-muted-foreground font-normal ml-2 text-sm">
                              · {d.seats} cadeira(s)
                            </span>
                          </p>
                        </div>
                      </div>
                      <ol className="space-y-1.5">
                        {eleitos.map((c, i) => (
                          <li key={c.id} className="flex items-center gap-2 sm:gap-3 px-2 py-1.5 rounded-md bg-emerald-500/5 border border-emerald-500/20">
                            <span className="text-emerald-400 font-bold tabular-nums shrink-0">{i + 1}º</span>
                            <CandidatePhoto candidateId={c.photo_id} name={c.urn_name} partyNumber={d.party.party_number} size="sm" />
                            <div className="flex-1 min-w-0">
                              <p className="font-semibold truncate text-sm flex items-center gap-2">
                                <span className="truncate">{c.urn_name}</span>
                                <ResultBadge status={c.result_status} size="sm" />
                              </p>
                              <p className="text-[11px] text-muted-foreground">
                                {numberFmt.format(c.votes)} votos
                              </p>
                            </div>
                            <span className="text-xs font-mono text-emerald-400 shrink-0">ELEITO</span>
                          </li>
                        ))}
                        {d.seats > eleitos.length && (
                          <li className="text-xs text-amber-400 px-2 py-1">
                            ⚠ {d.seats - eleitos.length} cadeira(s) sem candidato elegível (não atingiram 10% do QE).
                          </li>
                        )}
                      </ol>
                    </li>
                  );
                })}
            </ul>
          </section>

          {/* Disclaimer */}
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 flex gap-3 text-sm">
            <Info className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Simulação técnica baseada em dados históricos</p>
              <p className="text-xs text-muted-foreground mt-1">
                Esta projeção aplica as regras vigentes (Quociente Eleitoral + D'Hondt + cláusula de barreira + lei das sobras 14.211/2021) sobre o resultado real da última eleição na cidade selecionada. <strong>Não prevê o futuro</strong> — serve pra entender como o sistema distribui cadeiras dado um cenário de votos. Use o modo "editar votos" pra explorar cenários hipotéticos.
              </p>
            </div>
          </div>
        </>
      )}

      {selectedMuni && !loading && results && totalValidos === 0 && (
        <div className="rounded-xl border border-dashed border-border p-10 text-center bg-card/40">
          <p className="text-sm text-muted-foreground">
            Sem dados de votação pra {selectedMuni.name} no cargo selecionado.
          </p>
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------- StatCard

function StatCard({ label, value, tone }: { label: string; value: number; tone: "primary" | "emerald" | "muted" }) {
  const color = tone === "primary" ? "text-primary" : tone === "emerald" ? "text-emerald-400" : "text-foreground";
  return (
    <div className="rounded-lg border bg-card/60 px-4 py-3">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`text-2xl font-bold mt-0.5 tabular-nums ${color}`}>
        <AnimatedNumber value={value} />
      </p>
    </div>
  );
}

// ----------------------------------------------------------- PartyRow

function PartyRow({
  rank, d, qe, totalSeats, override, onOverride, onClearOverride,
}: {
  rank: number;
  d: DHondtResult;
  qe: number;
  totalSeats: number;
  override: number | undefined;
  onOverride: (v: number) => void;
  onClearOverride: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(String(d.party.total_votes));

  useEffect(() => {
    setDraft(String(d.party.total_votes));
  }, [d.party.total_votes]);

  const pctOfTotal = qe > 0 ? (d.party.total_votes / (qe * totalSeats)) * 100 : 0;
  const reachQE = d.party.total_votes / qe;

  return (
    <li className="px-3 sm:px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="w-6 text-center text-sm font-bold text-primary tabular-nums shrink-0">{rank}</span>
        <PartyLogo number={d.party.party_number} abbreviation={d.party.party_abbr} size="sm" />
        <div className="flex-1 min-w-0">
          <p className="font-semibold truncate">
            {d.party.party_abbr} <span className="text-xs text-muted-foreground font-normal">· {d.party.party_name}</span>
          </p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5 flex-wrap">
            <span className="tabular-nums">
              <AnimatedNumber value={d.party.total_votes} /> votos · {pctFmt.format(pctOfTotal)}%
            </span>
            <span className="tabular-nums">
              · {pctFmt.format(reachQE)} × QE
            </span>
            {override !== undefined && (
              <span className="text-amber-400">· editado</span>
            )}
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className={`text-2xl font-bold tabular-nums ${d.seats > 0 ? "text-emerald-400" : "text-muted-foreground"}`}>
            {d.seats}
          </p>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {d.passedBarrier ? "cadeiras" : "abaixo do QE"}
          </p>
        </div>
      </div>
      {/* Edit votos: e se */}
      {editing ? (
        <div className="mt-2 flex items-center gap-2">
          <input
            type="number"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="flex-1 py-1.5 px-2 rounded-md bg-background border border-border text-sm tabular-nums"
            min={0}
            autoFocus
          />
          <button
            onClick={() => {
              const v = parseInt(draft);
              if (!isNaN(v) && v >= 0) onOverride(v);
              setEditing(false);
            }}
            className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-semibold"
          >
            Aplicar
          </button>
          <button
            onClick={() => { setEditing(false); setDraft(String(d.party.total_votes)); }}
            className="px-3 py-1.5 rounded-md border border-border text-xs"
          >
            Cancelar
          </button>
        </div>
      ) : (
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-primary hover:underline"
          >
            ✎ Simular outro número de votos pra {d.party.party_abbr}
          </button>
          {override !== undefined && (
            <button
              onClick={onClearOverride}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              · resetar
            </button>
          )}
        </div>
      )}
    </li>
  );
}
