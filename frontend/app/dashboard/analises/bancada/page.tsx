"use client";

/**
 * Bancada por partido: quem já está no mandato e quem está entrando agora.
 *
 * Senado: a casa renova em partes, então há dois grupos de verdade — os
 * senadores eleitos em 2022 (seguem até 2031) e os eleitos em 2026.
 * Câmara: todo mundo é trocado; o mesmo quadro vira "bancada de 2022 x 2026".
 *
 * A REGRA QUE NÃO PODE QUEBRAR: quem só está À FRENTE numa UF que o TSE ainda
 * não fechou não é eleito. Aparece vazado no desenho e em coluna própria na
 * tabela — nunca somado aos eleitos.
 */
import { ArrowLeft, Landmark, Loader2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { partyColor } from "@/lib/partyColors";
import type { TseBancadaCadeira, TseBancadaResponse } from "@/lib/types";
import { type Assento, Hemiciclo } from "@/components/tse/Hemiciclo";
import { PresentButton } from "@/components/ui/PresentButton";

const numberFmt = new Intl.NumberFormat("pt-BR");

const ANO = 2026;
const CASAS = [
  { cargo: "5", label: "Senado" },
  { cargo: "6", label: "Câmara" },
];

// Enquanto houver UF sem resultado, o quadro muda sozinho: confere de novo.
const INTERVALO_MS = 120_000;

function titulo(c: TseBancadaCadeira, sufixo: string): string {
  return `${c.nome} (${c.sigla}/${c.uf}) — ${sufixo}`;
}

export default function BancadaPage() {
  const [cargo, setCargo] = useState("5");
  const [data, setData] = useState<TseBancadaResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState(false);
  // Destaque: o que está sob o mouse vale mais que o que foi fixado no clique.
  const [fixado, setFixado] = useState<number | null>(null);
  const [sobMouse, setSobMouse] = useState<number | null>(null);
  const pedido = useRef(0);

  const carregar = useCallback(
    (silencioso: boolean) => {
      const meu = ++pedido.current;
      if (silencioso) setAtualizando(true);
      else setLoading(true);
      api<TseBancadaResponse>(
        `/v1/tse/stats/bancada?year=${ANO}&office_code=${cargo}`,
        { skipCache: silencioso },
      )
        .then((d) => {
          if (meu !== pedido.current) return;
          setData(d);
          setErro(false);
        })
        .catch(() => {
          if (meu !== pedido.current) return;
          // Na atualização silenciosa, mantém o que já está na tela.
          if (!silencioso) {
            setData(null);
            setErro(true);
          }
        })
        .finally(() => {
          if (meu !== pedido.current) return;
          setLoading(false);
          setAtualizando(false);
        });
    },
    [cargo],
  );

  useEffect(() => {
    setFixado(null);
    setSobMouse(null);
    setData(null);
    carregar(false);
  }, [carregar]);

  const pendentes = data?.ufs_pendentes.length ?? 0;
  useEffect(() => {
    if (pendentes === 0) return;
    const t = setInterval(() => carregar(true), INTERVALO_MS);
    return () => clearInterval(t);
  }, [pendentes, carregar]);

  const destaque = sobMouse ?? fixado;
  const soma = data?.modo === "soma";

  // As cadeiras entram no desenho na ordem da tabela, para a fatia de cada
  // partido ficar no mesmo lugar nos dois hemiciclos.
  const { esquerda, direita } = useMemo(() => {
    if (!data) return { esquerda: [] as Assento[], direita: [] as Assento[] };
    const ordem = new Map(data.partidos.map((p, i) => [p.numero, i]));
    const porPartido = (a: TseBancadaCadeira, b: TseBancadaCadeira) =>
      (ordem.get(a.numero) ?? 99) - (ordem.get(b.numero) ?? 99);

    const antes = data.cadeiras
      .filter((c) => c.situacao === "antes")
      .sort((a, b) => porPartido(a, b) || b.votos - a.votos)
      .map<Assento>((c) => ({
        partido: c.numero,
        estado: "firme",
        titulo: titulo(
          c,
          data.modo === "soma"
            ? `no mandato, eleito em ${data.ano_anterior}`
            : `eleito em ${data.ano_anterior}`,
        ),
      }));

    // Dentro da fatia do partido, primeiro os eleitos (cheios) e depois quem
    // só está à frente (vazados): as duas coisas não se misturam no desenho.
    const peso = { eleitos: 0, a_frente: 1, antes: 2 } as const;
    const entrando = data.cadeiras
      .filter((c) => c.situacao !== "antes")
      .sort(
        (a, b) =>
          porPartido(a, b) ||
          peso[a.situacao] - peso[b.situacao] ||
          b.votos - a.votos,
      )
      .map<Assento>((c) => ({
        partido: c.numero,
        estado: c.situacao === "eleitos" ? "firme" : "parcial",
        titulo: titulo(
          c,
          c.situacao === "eleitos"
            ? `eleito em ${data.ano}`
            : "à frente, resultado ainda não proclamado",
        ),
      }));

    const semDono = Math.max(0, data.em_disputa - entrando.length);
    const vagas = Array.from({ length: semDono }, (): Assento => ({
      partido: null,
      estado: "vaga",
      titulo: "Cadeira ainda sem eleito proclamado",
    }));
    return { esquerda: antes, direita: [...entrando, ...vagas] };
  }, [data]);

  const mostrarAFrente = (data?.a_frente ?? 0) > 0;
  const definidas = data ? data.eleitos : 0;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <Link
        href="/dashboard/analises"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Análises
      </Link>

      <header className="mb-5 flex items-end justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-10 h-10 rounded-lg bg-primary/15 text-primary">
            <Landmark className="w-5 h-5" />
          </span>
          <div>
            <h1 className="text-2xl font-bold">Bancada {ANO}</h1>
            <p className="text-sm text-muted-foreground">
              {soma === false
                ? "A bancada que sai e a que entra, partido por partido."
                : "Quem já está no mandato e quem está entrando agora, por partido."}
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
            aria-label="Casa legislativa"
            className="inline-flex rounded-md border border-border bg-card p-0.5"
          >
            {CASAS.map((c) => (
              <button
                key={c.cargo}
                role="tab"
                aria-selected={cargo === c.cargo}
                onClick={() => setCargo(c.cargo)}
                className={
                  "px-3 py-1.5 text-sm rounded transition-colors " +
                  (cargo === c.cargo
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

      {loading && (
        <div className="h-[50vh] grid place-items-center">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {erro && !loading && (
        <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">
          Não foi possível carregar a bancada. Tente de novo em instantes.
        </div>
      )}

      {data && !loading && (
        <>
          {pendentes > 0 && (
            <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-sm">
              <span className="font-medium">Apuração em andamento.</span>{" "}
              {soma ? (
                <>
                  O TSE proclamou {numberFmt.format(definidas)} das{" "}
                  {numberFmt.format(data.em_disputa)} vagas. Nas outras{" "}
                  {numberFmt.format(data.a_frente)}, aparece quem está à frente
                  — ainda não é eleito.
                </>
              ) : (
                <>
                  {numberFmt.format(definidas)} deputados proclamados até agora,
                  em {data.ufs - pendentes} de {data.ufs} UFs.
                </>
              )}{" "}
              <span className="text-muted-foreground">
                Falta: {data.ufs_pendentes.join(", ")}.
              </span>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
            <section className="lg:col-span-3 rounded-lg border bg-card p-5">
              <div className="grid grid-cols-5 gap-4 items-end">
                <figure className="col-span-2">
                  <Hemiciclo
                    assentos={esquerda}
                    destaque={destaque}
                    onPassar={setSobMouse}
                    onClicar={(n) => setFixado((f) => (f === n ? null : n))}
                    rotulo={`${esquerda.length} cadeiras de ${data.ano_anterior}`}
                    className="w-full h-auto text-foreground"
                  />
                  <figcaption className="mt-3 text-center">
                    <p className="text-xs font-semibold uppercase tracking-wider">
                      {soma ? "No mandato" : `Eleita em ${data.ano_anterior}`}
                    </p>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      {numberFmt.format(data.antes)}{" "}
                      {soma ? `· eleitos em ${data.ano_anterior}` : "deputados"}
                    </p>
                  </figcaption>
                </figure>
                <figure className="col-span-3">
                  <Hemiciclo
                    assentos={direita}
                    destaque={destaque}
                    onPassar={setSobMouse}
                    onClicar={(n) => setFixado((f) => (f === n ? null : n))}
                    rotulo={`${direita.length} cadeiras em disputa em ${data.ano}`}
                    className="w-full h-auto text-foreground"
                  />
                  <figcaption className="mt-3 text-center">
                    <p className="text-xs font-semibold uppercase tracking-wider">
                      {mostrarAFrente ? "Eleitos e à frente" : `Eleitos em ${data.ano}`}
                    </p>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      {numberFmt.format(definidas)} de{" "}
                      {numberFmt.format(data.em_disputa)}
                      {mostrarAFrente && ` · ${numberFmt.format(data.a_frente)} à frente`}
                    </p>
                  </figcaption>
                </figure>
              </div>

              <div className="mt-5 flex items-center justify-center gap-5 flex-wrap text-[11px] text-muted-foreground">
                <Legenda estado="firme" texto={soma ? "no mandato ou eleito" : "eleito"} />
                {mostrarAFrente && (
                  <Legenda estado="parcial" texto="à frente, ainda não proclamado" />
                )}
                {direita.some((a) => a.estado === "vaga") && (
                  <Legenda estado="vaga" texto="cadeira sem resultado" />
                )}
              </div>
            </section>

            <section className="lg:col-span-2 rounded-lg border bg-card p-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    <th className="text-left font-medium pb-2 pl-2">Partido</th>
                    <th className="text-right font-medium pb-2 px-2">
                      {soma ? "Mandato" : data.ano_anterior}
                    </th>
                    <th className="text-right font-medium pb-2 px-2">
                      {soma ? "Eleitos" : data.ano}
                    </th>
                    {mostrarAFrente && (
                      <th className="text-right font-medium pb-2 px-2 whitespace-nowrap">À frente</th>
                    )}
                    {soma && <th className="text-right font-medium pb-2 pr-2">Total</th>}
                  </tr>
                </thead>
                <tbody>
                  {data.partidos.map((p) => {
                    const ativo = destaque === p.numero;
                    const apagado = destaque != null && !ativo;
                    return (
                      <tr
                        key={p.numero}
                        onMouseEnter={() => setSobMouse(p.numero)}
                        onMouseLeave={() => setSobMouse(null)}
                        onClick={() => setFixado((f) => (f === p.numero ? null : p.numero))}
                        className={
                          "cursor-pointer transition-opacity " +
                          (ativo ? "bg-primary/10" : "hover:bg-accent/50") +
                          (apagado ? " opacity-40" : "")
                        }
                      >
                        <td className="py-1.5 pl-2 rounded-l">
                          <span className="flex items-center gap-2 min-w-0">
                            <span
                              className="w-1.5 h-5 rounded-full shrink-0"
                              style={{ background: partyColor(p.numero) }}
                            />
                            <span className="font-medium truncate">{p.sigla}</span>
                          </span>
                        </td>
                        <Num v={p.antes} />
                        <Num v={p.eleitos} forte={!soma} />
                        {mostrarAFrente && <Num v={p.a_frente} suave />}
                        {soma && <Num v={p.total} forte ultimo />}
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border text-muted-foreground">
                    <td className="pt-2 pl-2 text-xs uppercase tracking-wider">Total</td>
                    <Num v={data.antes} rodape />
                    <Num v={data.eleitos} rodape />
                    {mostrarAFrente && <Num v={data.a_frente} rodape />}
                    {soma && (
                      <Num v={data.antes + data.eleitos + data.a_frente} rodape ultimo />
                    )}
                  </tr>
                </tfoot>
              </table>
            </section>
          </div>

          <p className="mt-4 text-xs text-muted-foreground leading-relaxed max-w-4xl">
            {data.observacao}
          </p>
        </>
      )}
    </div>
  );
}

function Num({
  v, forte, suave, rodape, ultimo,
}: {
  v: number;
  forte?: boolean;
  suave?: boolean;
  rodape?: boolean;
  ultimo?: boolean;
}) {
  return (
    <td
      className={
        "text-right tabular-nums " +
        (rodape ? "pt-2 " : "py-1.5 ") +
        (ultimo ? "pr-2 rounded-r " : "px-2 ") +
        (forte ? "font-bold " : "") +
        (suave || v === 0 ? "text-muted-foreground" : "")
      }
    >
      {v === 0 && !rodape ? "–" : numberFmt.format(v)}
    </td>
  );
}

function Legenda({ estado, texto }: { estado: Assento["estado"]; texto: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg viewBox="0 0 12 12" className="w-3 h-3 text-foreground" aria-hidden>
        {estado === "firme" && <circle cx="6" cy="6" r="5" fill="currentColor" opacity="0.75" />}
        {estado === "parcial" && (
          <circle cx="6" cy="6" r="4" fill="currentColor" fillOpacity="0.22"
            stroke="currentColor" strokeWidth="1.8" />
        )}
        {estado === "vaga" && (
          <circle cx="6" cy="6" r="4" fill="none" stroke="currentColor"
            strokeWidth="1.6" strokeOpacity="0.35" strokeDasharray="2 2" />
        )}
      </svg>
      {texto}
    </span>
  );
}
