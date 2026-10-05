"use client";

/**
 * Placar da apuração: os candidatos em cartões grandes, com foto, barra e
 * percentual — e, ao lado, abstenção, brancos e nulos comparados com as
 * eleições anteriores.
 *
 * É a mesma informação da Análise de Eleição, arrumada para ser lida de longe
 * (TV, projetor, reunião). O botão Apresentar tira o resto da tela.
 *
 * DE ONDE VEM CADA NÚMERO:
 *  - votos: /tse/election-results. Presidente no Brasil e governador/senador
 *    na UF usam o total oficial do candidato, atualizado a cada 2 minutos.
 *    Presidente RECORTADO POR UF é a soma dos municípios, que só anda quando a
 *    varredura passa — por isso a tela avisa quando é esse o caso.
 *  - urnas apuradas, abstenção, brancos e nulos: /tse/stats/turnout, que na
 *    apuração lê o mesmo arquivo do TSE que alimenta o placar.
 */
import { ArrowLeft, ArrowRight, Loader2, RefreshCw, Tv } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { ANO_EM_APURACAO } from "@/lib/elections";
import { partyColor } from "@/lib/partyColors";
import {
  classifyResult,
  type TseElectionResults,
  type TseTurnoutAno,
  type TseTurnoutResponse,
} from "@/lib/types";
import { CandidatePhoto } from "@/components/tse/CandidatePhoto";
import { ResultBadge } from "@/components/tse/ResultBadge";
import { PresentButton } from "@/components/ui/PresentButton";

const numberFmt = new Intl.NumberFormat("pt-BR");
const pctFmt = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const ANO = 2026;
const PRESIDENTE = "1";

const CARGOS = [
  { value: "1", label: "Presidente" },
  { value: "3", label: "Governador" },
  { value: "5", label: "Senador" },
];

const REGIOES: { nome: string; ufs: string[] }[] = [
  { nome: "Norte", ufs: ["AC", "AM", "AP", "PA", "RO", "RR", "TO"] },
  { nome: "Nordeste", ufs: ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"] },
  { nome: "Centro-Oeste", ufs: ["DF", "GO", "MS", "MT"] },
  { nome: "Sudeste", ufs: ["ES", "MG", "RJ", "SP"] },
  { nome: "Sul", ufs: ["PR", "RS", "SC"] },
];

// Governador e senador são disputados dentro de uma UF: precisam de uma.
const UF_INICIAL = "RJ";
const INTERVALO_MS = 120_000;
const PRIMEIROS = 5;

export default function PlacarPage() {
  const [cargo, setCargo] = useState(PRESIDENTE);
  // "" = Brasil (só faz sentido para presidente).
  const [uf, setUf] = useState("");
  const [res, setRes] = useState<TseElectionResults | null>(null);
  const [turnout, setTurnout] = useState<TseTurnoutResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState(false);
  const [todos, setTodos] = useState(false);
  const pedido = useRef(0);

  const carregar = useCallback(
    (silencioso: boolean) => {
      const meu = ++pedido.current;
      if (silencioso) setAtualizando(true);
      else setLoading(true);
      const recorte = uf ? `&state=${uf}` : "";
      const opts = { skipCache: silencioso };
      Promise.all([
        api<TseElectionResults>(
          `/v1/tse/election-results?year=${ANO}&office_code=${cargo}&limit=60${recorte}`,
          opts,
        ),
        // O comparecimento é acessório: se falhar, o placar aparece assim mesmo.
        api<TseTurnoutResponse>(
          `/v1/tse/stats/turnout?office_code=${cargo}&uf=${uf || "BR"}`,
          opts,
        ).catch(() => null),
      ])
        .then(([r, t]) => {
          if (meu !== pedido.current) return;
          setRes(r);
          // Na atualização automática, uma falha passageira do comparecimento
          // não pode apagar o que já estava na tela: sem ele `parcial` vira
          // false, o intervalo é desligado e o placar para de se atualizar
          // sozinho até alguém recarregar a página.
          setTurnout((antes) => t ?? (silencioso ? antes : null));
          setErro(false);
        })
        .catch(() => {
          if (meu !== pedido.current) return;
          if (!silencioso) {
            setRes(null);
            setErro(true);
          }
        })
        .finally(() => {
          if (meu !== pedido.current) return;
          setLoading(false);
          setAtualizando(false);
        });
    },
    [cargo, uf],
  );

  useEffect(() => {
    setTodos(false);
    carregar(false);
  }, [carregar]);

  const anoAtual = turnout?.anos.find((a) => a.ano === ANO) ?? null;
  const parcial = anoAtual?.parcial ?? false;
  // Segue atualizando enquanto a apuração não fechar. Sem a linha do
  // comparecimento (falhou na primeira carga, ou o recorte ainda não tem)
  // não dá para saber se fechou — e, na dúvida, durante a eleição em apuração,
  // continua: parar em silêncio deixaria a tela da TV congelada.
  const acompanhar = anoAtual ? parcial : ANO_EM_APURACAO === ANO;
  useEffect(() => {
    if (!acompanhar) return;
    const t = setInterval(() => carregar(true), INTERVALO_MS);
    return () => clearInterval(t);
  }, [acompanhar, carregar]);

  function trocarCargo(novo: string) {
    setCargo(novo);
    // Presidente abre no país; os outros cargos não existem sem UF.
    if (novo === PRESIDENTE) setUf("");
    else if (!uf) setUf(UF_INICIAL);
  }

  const cargoNome = CARGOS.find((c) => c.value === cargo)?.label ?? "";
  const lugar = uf || "Brasil";
  const total = res?.total_votes || 0;
  const lista = res ? (todos ? res.results : res.results.slice(0, PRIMEIROS)) : [];
  const presidentePorUf = cargo === PRESIDENTE && uf !== "";

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-4 flex items-end justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
            <Tv className="w-5 h-5" />
          </span>
          <div>
            <h1 className="text-2xl font-bold">
              {cargoNome} <span className="text-muted-foreground font-normal">|</span>{" "}
              {lugar}
            </h1>
            <p className="text-sm text-muted-foreground">
              Placar da apuração de {ANO}, 1º turno.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PresentButton />
          <button
            onClick={() => carregar(true)}
            disabled={loading || atualizando}
            title="Atualizar"
            aria-label="Atualizar"
            className="grid place-items-center w-9 h-9 rounded-md bg-card border border-border hover:border-primary/60 hover:text-primary transition-colors disabled:opacity-50"
          >
            <RefreshCw className={"w-4 h-4" + (atualizando ? " animate-spin" : "")} />
          </button>
          <div
            role="tablist"
            aria-label="Cargo"
            className="inline-flex rounded-md border border-border bg-card p-0.5"
          >
            {CARGOS.map((c) => (
              <button
                key={c.value}
                role="tab"
                aria-selected={cargo === c.value}
                onClick={() => trocarCargo(c.value)}
                className={
                  "px-3 py-1.5 text-sm rounded transition-colors " +
                  (cargo === c.value
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground")
                }
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Recorte: Brasil (só presidente) ou uma UF, agrupadas por região. */}
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        {cargo === PRESIDENTE && (
          <Chip ativo={uf === ""} onClick={() => setUf("")}>
            Brasil
          </Chip>
        )}
        {REGIOES.map((r) => (
          <div key={r.nome} className="flex items-center gap-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-0.5">
              {r.nome}
            </span>
            {r.ufs.map((u) => (
              <Chip key={u} ativo={uf === u} onClick={() => setUf(u)}>
                {u}
              </Chip>
            ))}
          </div>
        ))}
      </div>

      {/* Quanto da apuração já entrou */}
      {/* Some durante a troca de recorte: o percentual que está em memória é
          o do recorte ANTERIOR, e ficaria sob o título do novo. */}
      {!loading && !erro && anoAtual?.pct_secoes != null && (
        <div className="mb-4 rounded-lg border bg-card px-4 py-3">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="uppercase tracking-wider text-xs text-muted-foreground">
              Urnas apuradas
            </span>
            <span className="font-bold tabular-nums">
              {pctFmt.format(anoAtual.pct_secoes)}%
            </span>
          </div>
          <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-700"
              style={{ width: `${Math.min(100, anoAtual.pct_secoes)}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Fonte: TSE.
            {parcial && " Atualiza sozinho a cada 2 minutos enquanto a apuração não fecha."}
          </p>
        </div>
      )}

      {loading && (
        <div className="h-[40vh] grid place-items-center">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {erro && !loading && (
        <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">
          Não foi possível carregar o placar. Tente de novo em instantes.
        </div>
      )}

      {res && !loading && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          <section className="lg:col-span-3 space-y-2.5">
            {res.results.length === 0 && (
              <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
                Sem votos de {cargoNome.toLowerCase()} em {lugar} ainda.
              </div>
            )}

            {lista.map((r) => {
              const pct = total > 0 ? (100 * r.votes) / total : 0;
              const situacao = classifyResult(r.candidate.result_status);
              // Só destaca quem o TSE já definiu: eleito, ou classificado para
              // o 2º turno. Liderar a contagem não é destaque.
              const destaque = situacao === "elected" || situacao === "runoff";
              const cor = partyColor(r.candidate.party.number);
              return (
                <article
                  key={r.candidate.id}
                  className={
                    "flex items-center gap-3 sm:gap-4 rounded-xl border p-3 sm:p-4 transition-colors " +
                    (destaque ? "bg-primary/10 border-primary/40" : "bg-card")
                  }
                >
                  <CandidatePhoto
                    candidateId={r.candidate.id}
                    name={r.candidate.urn_name}
                    partyNumber={r.candidate.party.number}
                    size="lg"
                    className="shrink-0 !w-14 !h-14 sm:!w-20 sm:!h-20"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="flex items-center gap-2 flex-wrap text-xs sm:text-sm font-semibold uppercase tracking-wide">
                      <span className="truncate">{r.candidate.urn_name}</span>
                      <span className="text-muted-foreground font-normal">|</span>
                      {/* A sigla fica na cor do texto, com o partido numa
                          bolinha: pintar a sigla na cor do partido deixava o
                          azul-marinho do PL ilegível no tema escuro. */}
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="w-2.5 h-2.5 rounded-full ring-1 ring-foreground/25"
                          style={{ background: cor }}
                        />
                        {r.candidate.party.abbreviation}
                      </span>
                      <ResultBadge status={r.candidate.result_status} size="sm" />
                    </p>
                    <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full transition-[width] duration-700"
                        style={{ width: `${Math.min(100, pct)}%`, background: cor }}
                      />
                    </div>
                    <p className="mt-1.5 text-sm tabular-nums">
                      <strong>{numberFmt.format(r.votes)}</strong>{" "}
                      <span className="text-xs text-muted-foreground uppercase tracking-wide">
                        votos
                      </span>
                    </p>
                  </div>
                  <p className="shrink-0 text-2xl sm:text-4xl font-bold tabular-nums">
                    {pctFmt.format(pct)}
                    <span className="text-lg sm:text-2xl">%</span>
                  </p>
                </article>
              );
            })}

            <div className="flex items-center justify-between gap-3 pt-1 text-sm">
              {res.results.length > PRIMEIROS ? (
                <button
                  onClick={() => setTodos((t) => !t)}
                  className="text-primary hover:underline"
                >
                  {todos
                    ? "Mostrar só os primeiros"
                    : `Ver todos os ${res.results.length} candidatos`}
                </button>
              ) : (
                <span />
              )}
              <Link
                href={`/dashboard/analises/eleicao?ano=${ANO}&cargo=${cargo}&uf=${uf}`}
                className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
              >
                Resultado completo <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Percentual sobre os votos válidos do cargo
              {cargo === "5" && " (cada eleitor vota em dois senadores)"}.
              {presidentePorUf &&
                " Presidente recortado por UF é a soma dos municípios, atualizada a cada varredura: pode estar alguns minutos atrás do placar nacional."}
            </p>
          </section>

          <aside className="lg:col-span-2">
            <Comparecimento turnout={turnout} lugar={lugar} />
          </aside>
        </div>
      )}
    </div>
  );
}

function Chip({
  ativo, onClick, children,
}: {
  ativo: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={ativo}
      className={
        "px-2 py-0.5 rounded text-xs transition-colors " +
        (ativo
          ? "bg-primary text-primary-foreground font-semibold"
          : "text-muted-foreground hover:text-foreground hover:bg-accent/60")
      }
    >
      {children}
    </button>
  );
}

// ------------------------------------------------------------ comparecimento

const METRICAS: { chave: "pct_abstencao" | "pct_brancos" | "pct_nulos"; nome: string }[] = [
  { chave: "pct_abstencao", nome: "Abstenção" },
  { chave: "pct_brancos", nome: "Brancos" },
  { chave: "pct_nulos", nome: "Nulos" },
];

function Comparecimento({
  turnout, lugar,
}: {
  turnout: TseTurnoutResponse | null;
  lugar: string;
}) {
  // As três eleições mais recentes do mesmo cargo, da mais antiga para a atual.
  const anos = (turnout?.anos ?? []).slice(-3);
  const atual = anos[anos.length - 1];

  if (!atual) {
    return (
      <div className="rounded-lg border bg-card p-5 text-sm text-muted-foreground">
        Sem dado de comparecimento para este recorte.
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card p-4 sm:p-5">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">
        Abstenção, brancos e nulos · {lugar}
      </p>

      <div className="mt-4 grid grid-cols-3 gap-4 sm:gap-6">
        {METRICAS.map((m) => (
          <Barras key={m.chave} nome={m.nome} anos={anos} chave={m.chave} />
        ))}
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-2 text-sm border-t border-border pt-4">
        <Dado rotulo="Eleitorado" valor={atual.eleitorado} />
        <Dado rotulo="Compareceram" valor={atual.comparecimento} />
        <Dado rotulo="Não foram votar" valor={atual.abstencao} />
        <Dado rotulo="Votos válidos" valor={atual.validos} />
        {/* Só aparece onde existe: explica por que válidos + brancos + nulos
            não fecha com o comparecimento. */}
        {atual.anulados > 0 && (
          <Dado rotulo="Anulados (sub judice)" valor={atual.anulados} />
        )}
      </dl>

      <p className="mt-3 text-[11px] text-muted-foreground leading-relaxed">
        Números de {atual.ano}
        {atual.parcial && " (apuração parcial — ainda sobem)"}. Abstenção sobre
        quem estava apto nas seções já apuradas; brancos e nulos sobre o total
        de votos do cargo.
      </p>
    </div>
  );
}

function Barras({
  nome, anos, chave,
}: {
  nome: string;
  anos: TseTurnoutAno[];
  chave: "pct_abstencao" | "pct_brancos" | "pct_nulos";
}) {
  // Escala própria de cada grupo, com folga: senão brancos (2%) sumiria ao
  // lado da abstenção (20%) e a comparação entre os anos não se leria.
  const maior = Math.max(1, ...anos.map((a) => a[chave] ?? 0));
  const teto = maior * 1.35;
  return (
    <div className="min-w-0">
      {/* O "%" fica no título, não em cada número: com ele o rótulo passava da
          largura da barra e encostava no do grupo vizinho. */}
      <p className="text-center text-xs font-semibold uppercase tracking-wide">
        {nome} <span className="font-normal text-muted-foreground">%</span>
      </p>
      <div className="mt-2 flex items-end justify-center gap-1 h-36">
        {anos.map((a, i) => {
          const v = a[chave];
          const atual = i === anos.length - 1;
          return (
            <div
              key={a.ano}
              className="flex flex-col items-center justify-end h-full flex-1 min-w-0 max-w-[2.75rem]"
            >
              <span
                className={
                  "text-[10px] tabular-nums whitespace-nowrap mb-1 " +
                  (atual ? "font-bold" : "text-muted-foreground")
                }
              >
                {v == null ? "–" : pctFmt.format(v)}
              </span>
              <div className="w-4 flex-1 rounded-full bg-muted flex items-end overflow-hidden">
                <div
                  className={
                    "w-full rounded-full transition-[height] duration-700 " +
                    (atual ? "bg-primary" : i === anos.length - 2 ? "bg-primary/55" : "bg-primary/30")
                  }
                  style={{ height: `${v == null ? 0 : Math.max(3, (100 * v) / teto)}%` }}
                />
              </div>
              <span className="mt-1 text-[11px] text-muted-foreground tabular-nums">
                {a.ano}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Dado({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {rotulo}
      </dt>
      <dd className="font-semibold tabular-nums">{numberFmt.format(valor)}</dd>
    </div>
  );
}
