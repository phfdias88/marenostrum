"use client";

/**
 * Mapa da virada: em quais municípios o partido mais votado mudou entre a
 * eleição passada e a de agora.
 *
 * O mapa partidário mostra quem ganhou. Este mostra o que MUDOU — que é a
 * pergunta de quem planeja a próxima campanha: onde o terreno se moveu.
 *
 * Cada cargo compara com a última eleição das MESMAS vagas. Presidente e
 * governador, com 2022. Senador, com 2018: as duas cadeiras por UF em disputa
 * em 2026 são as de 2018 — em 2022 a eleição foi da outra, de uma vaga só, e
 * comparar com ela seria comparar disputas diferentes.
 */
import { ArrowLeft, ArrowRight, Loader2, Repeat2, X } from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { partyColor } from "@/lib/partyColors";
import type { TseViradaResponse } from "@/lib/types";
import type { ViradaFiltro } from "@/components/map/ViradaMap";
import { PresentButton } from "@/components/ui/PresentButton";

const ViradaMap = dynamic(() => import("@/components/map/ViradaMap"), {
  ssr: false,
  loading: () => (
    <div className="h-full grid place-items-center text-muted-foreground">
      Carregando mapa…
    </div>
  ),
});

const numberFmt = new Intl.NumberFormat("pt-BR");
const pctFmt = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  maximumFractionDigits: 1,
});

const PARA = 2026;

const OPTIONS = [
  { value: "1", label: "Presidente", de: 2022 },
  { value: "3", label: "Governador", de: 2022 },
  { value: "5", label: "Senador", de: 2018 },
];

// Mesmos atalhos do mapa partidário.
const UF_CHIPS: { uf: string; label: string; lat: number; lng: number; zoom: number }[] = [
  { uf: "BR", label: "Brasil", lat: -14.5, lng: -52.0, zoom: 4 },
  { uf: "SP", label: "SP", lat: -22.5, lng: -48.5, zoom: 7 },
  { uf: "RJ", label: "RJ", lat: -22.3, lng: -42.7, zoom: 7 },
  { uf: "MG", label: "MG", lat: -18.5, lng: -44.5, zoom: 6 },
  { uf: "BA", label: "BA", lat: -12.5, lng: -41.5, zoom: 6 },
  { uf: "RS", label: "RS", lat: -30.0, lng: -53.5, zoom: 6 },
  { uf: "PR", label: "PR", lat: -25.0, lng: -51.5, zoom: 7 },
  { uf: "PE", label: "PE", lat: -8.5, lng: -38.0, zoom: 7 },
];

function mesmoFiltro(a: ViradaFiltro | null, b: ViradaFiltro): boolean {
  if (!a || a.tipo !== b.tipo) return false;
  if (a.tipo === "transicao" && b.tipo === "transicao") return a.chave === b.chave;
  return true;
}

export default function ViradaPage() {
  const [cargo, setCargo] = useState("1");
  const [data, setData] = useState<TseViradaResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(false);
  const [filtro, setFiltro] = useState<ViradaFiltro | null>(null);
  const [focusReq, setFocusReq] = useState<
    { lat: number; lng: number; zoom: number; key: number } | null
  >(null);

  const opcao = OPTIONS.find((o) => o.value === cargo) ?? OPTIONS[0];
  const de = opcao.de;

  useEffect(() => {
    let vivo = true;
    setLoading(true);
    setErro(false);
    setFiltro(null);
    // Sem isto, ao trocar de cargo o mapa antigo ficaria sob o título novo.
    setData(null);
    api<TseViradaResponse>(
      `/v1/tse/stats/virada?office_code=${cargo}&from_year=${de}&to_year=${PARA}`,
    )
      .then((d) => vivo && setData(d))
      .catch(() => {
        if (!vivo) return;
        setData(null);
        setErro(true);
      })
      .finally(() => vivo && setLoading(false));
    return () => {
      vivo = false;
    };
  }, [cargo, de]);

  const viradas = useMemo(
    () => (data ? data.transicoes.filter((t) => t.virou).slice(0, 10) : []),
    [data],
  );
  const mantidas = useMemo(
    () => (data ? data.transicoes.filter((t) => !t.virou).slice(0, 6) : []),
    [data],
  );

  function alternar(f: ViradaFiltro) {
    setFiltro((atual) => (mesmoFiltro(atual, f) ? null : f));
  }

  const cargoNome = opcao.label;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-4 flex items-end justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
            <Repeat2 className="w-5 h-5" />
          </span>
          <div>
            <h1 className="text-2xl font-bold">
              Mapa da virada · {de} → {PARA}
            </h1>
            <p className="text-sm text-muted-foreground">
              Onde o partido mais votado para {cargoNome.toLowerCase()} mudou de
              uma eleição para a outra. 1º turno dos dois lados.
              {cargo === "5" &&
                " Senador compara com 2018, a última vez em que estas mesmas duas vagas por UF foram disputadas; vale o candidato mais votado em cada município."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PresentButton />
          <select
            value={cargo}
            onChange={(e) => setCargo(e.target.value)}
            aria-label="Cargo"
            className="py-2 px-3 rounded-md bg-card border border-border focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            {OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="mb-3 flex items-center gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {UF_CHIPS.map((c) => (
          <button
            key={c.uf}
            onClick={() =>
              setFocusReq({ lat: c.lat, lng: c.lng, zoom: c.zoom, key: Date.now() })
            }
            className="px-3 py-1 rounded-full bg-card border border-border text-xs hover:border-primary/60 hover:text-primary transition-colors shrink-0"
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3">
          <div className="h-[70vh] rounded-lg border border-border overflow-hidden relative">
            {loading && (
              <div className="absolute inset-0 z-[500] grid place-items-center bg-background/60">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            )}
            {erro && !loading && (
              <div className="absolute inset-0 z-[500] grid place-items-center p-6 text-center text-sm text-muted-foreground">
                Não foi possível carregar a comparação. Tente de novo em instantes.
              </div>
            )}
            {data && (
              <ViradaMap
                points={data.pontos}
                anoAntes={data.de}
                anoDepois={data.para}
                highlighted={filtro}
                focusRequest={focusReq}
              />
            )}

          </div>
        </div>

        <aside className="lg:col-span-1 space-y-4">
          {/* Placar */}
          <div className="rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                {data ? numberFmt.format(data.municipios) : "…"} municípios
              </p>
              {filtro && (
                <button
                  onClick={() => setFiltro(null)}
                  className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                >
                  <X className="w-3 h-3" /> limpar
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Placar
                label="viraram"
                valor={data?.viraram}
                total={data?.municipios}
                ativo={filtro?.tipo === "viraram"}
                onClick={() => alternar({ tipo: "viraram" })}
              />
              <Placar
                label="mantiveram"
                valor={data?.mantiveram}
                total={data?.municipios}
                ativo={filtro?.tipo === "mantiveram"}
                onClick={() => alternar({ tipo: "mantiveram" })}
              />
            </div>
            {/* Como ler o mapa. Fica aqui, e não por cima do mapa, para o
                canto dele ficar livre para o seletor de camada. */}
            <div className="mt-3 space-y-1 text-[11px] text-muted-foreground">
              <p className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-foreground/70 ring-1 ring-foreground/40 ring-offset-1 ring-offset-card" />
                virou — maior, na cor de quem passou a ganhar
              </p>
              <p className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-foreground/30 mx-0.5" />
                manteve o partido
              </p>
            </div>
          </div>

          {/* Para onde foi */}
          <div className="rounded-lg border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Maiores viradas
            </p>
            {data && viradas.length === 0 && (
              <p className="text-sm text-muted-foreground">
                {data.municipios === 0
                  ? `Ainda não há resultado por município de ${data.para} para este cargo.`
                  : "Nenhum município mudou de partido."}
              </p>
            )}
            <ul className="space-y-1">
              {viradas.map((t) => (
                <Transicao
                  key={t.chave}
                  t={t}
                  ativo={filtro?.tipo === "transicao" && filtro.chave === t.chave}
                  apagado={filtro != null && !(filtro.tipo === "transicao" && filtro.chave === t.chave)}
                  onClick={() => alternar({ tipo: "transicao", chave: t.chave })}
                />
              ))}
            </ul>

            {mantidas.length > 0 && (
              <>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mt-4 mb-2">
                  Onde nada mudou
                </p>
                <ul className="space-y-1">
                  {mantidas.map((t) => (
                    <Transicao
                      key={t.chave}
                      t={t}
                      ativo={filtro?.tipo === "transicao" && filtro.chave === t.chave}
                      apagado={filtro != null && !(filtro.tipo === "transicao" && filtro.chave === t.chave)}
                      onClick={() => alternar({ tipo: "transicao", chave: t.chave })}
                    />
                  ))}
                </ul>
              </>
            )}

            <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
              Clique numa linha para ver só esses municípios no mapa. Partido que
              se fundiu conta como o sucessor (
              {de < 2022 ? "PSL e DEM → União; " : ""}PTB e Patriota → PRD).
              {data && data.sem_comparacao > 0 && (
                <>
                  {" "}
                  {numberFmt.format(data.sem_comparacao)} município
                  {data.sem_comparacao > 1 ? "s" : ""} sem resultado em um dos
                  anos {data.sem_comparacao > 1 ? "ficaram" : "ficou"} de fora.
                </>
              )}
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Placar({
  label, valor, total, ativo, onClick,
}: {
  label: string;
  valor?: number;
  total?: number;
  ativo: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={ativo}
      className={
        "rounded-md px-3 py-2 text-left transition-all " +
        (ativo ? "bg-primary/15 ring-1 ring-primary/40" : "bg-accent/40 hover:bg-accent/70")
      }
    >
      <p className="text-xl font-bold tabular-nums leading-tight">
        {valor == null ? "…" : numberFmt.format(valor)}
      </p>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
        {valor != null && total ? ` · ${pctFmt.format(valor / total)}` : ""}
      </p>
    </button>
  );
}

function Transicao({
  t, ativo, apagado, onClick,
}: {
  t: TseViradaResponse["transicoes"][number];
  ativo: boolean;
  apagado: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        onClick={onClick}
        aria-pressed={ativo}
        className={
          "w-full flex items-center justify-between gap-2 text-sm rounded px-2 py-1 transition-all " +
          (ativo
            ? "bg-primary/15 ring-1 ring-primary/40"
            : "hover:bg-accent/60 " + (apagado ? "opacity-40" : ""))
        }
      >
        <span className="flex items-center gap-1.5 min-w-0">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ background: partyColor(t.de.numero) }}
          />
          <span className="font-medium truncate">{t.de.sigla}</span>
          {t.virou && (
            <>
              <ArrowRight className="w-3 h-3 text-muted-foreground shrink-0" />
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ background: partyColor(t.para.numero) }}
              />
              <span className="font-medium truncate">{t.para.sigla}</span>
            </>
          )}
        </span>
        <span className="text-muted-foreground tabular-nums shrink-0">
          {numberFmt.format(t.municipios)}
        </span>
      </button>
    </li>
  );
}
