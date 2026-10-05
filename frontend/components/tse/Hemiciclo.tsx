"use client";

/**
 * Hemiciclo: uma bolinha por cadeira, em arcos concêntricos, pintada pela cor
 * do partido. É o desenho clássico de plenário — quem olha entende o tamanho
 * de cada bancada sem ler número nenhum.
 *
 * As cadeiras chegam JÁ NA ORDEM em que devem aparecer (da esquerda para a
 * direita). Aqui só se decide ONDE fica cada bolinha: as posições são varridas
 * por ângulo, então partidos vizinhos na lista viram fatias vizinhas no arco.
 *
 * SVG puro, sem biblioteca: são no máximo ~500 círculos.
 */
import { partyColor } from "@/lib/partyColors";

export type Assento = {
  /** Número do partido; null = cadeira ainda sem dono (resultado não proclamado). */
  partido: number | null;
  /** "firme" = no mandato ou eleito; "parcial" = à frente, ainda não proclamado. */
  estado: "firme" | "parcial" | "vaga";
  /** Texto do tooltip nativo. */
  titulo: string;
};

type Posicao = { x: number; y: number; angulo: number; raio: number };

const RAIO_INTERNO = 0.38;

/**
 * Quantos arcos usar para `n` cadeiras.
 *
 * Com poucos arcos as bolinhas se apertam ao longo do arco; com muitos, os
 * arcos é que se apertam entre si. O desenho fica uniforme quando as duas
 * distâncias se igualam — então escolhe-se a quantidade em que elas ficam mais
 * próximas.
 */
function arcosPara(n: number): number {
  const raioMedio = (1 + RAIO_INTERNO) / 2;
  let melhor = 2;
  let menorDiferenca = Infinity;
  for (let r = 2; r <= 24; r++) {
    const entreArcos = (1 - RAIO_INTERNO) / (r - 1);
    const noArco = (Math.PI * raioMedio * r) / n;
    const diferenca = Math.abs(entreArcos - noArco);
    if (diferenca < menorDiferenca) {
      menorDiferenca = diferenca;
      melhor = r;
    }
  }
  return melhor;
}

export function posicoesDoHemiciclo(n: number): { pontos: Posicao[]; raioDaBolinha: number } {
  if (n <= 0) return { pontos: [], raioDaBolinha: 0 };

  const arcos = n < 4 ? 1 : arcosPara(n);
  const raios = Array.from({ length: arcos }, (_, i) =>
    arcos === 1 ? 0.75 : RAIO_INTERNO + ((1 - RAIO_INTERNO) * i) / (arcos - 1),
  );

  // Cadeiras por arco, proporcionais ao comprimento dele (maiores restos).
  const soma = raios.reduce((s, r) => s + r, 0);
  const ideal = raios.map((r) => (n * r) / soma);
  const porArco = ideal.map(Math.floor);
  let faltam = n - porArco.reduce((s, v) => s + v, 0);
  const ordemDosRestos = ideal
    .map((v, i) => ({ i, resto: v - Math.floor(v) }))
    .sort((a, b) => b.resto - a.resto);
  for (let k = 0; faltam > 0; k++, faltam--) porArco[ordemDosRestos[k % arcos].i]++;

  const pontos: Posicao[] = [];
  raios.forEach((raio, i) => {
    const qtd = porArco[i];
    for (let k = 0; k < qtd; k++) {
      // Da esquerda (π) para a direita (0), com meia folga em cada ponta.
      const angulo = Math.PI - (Math.PI * (k + 0.5)) / qtd;
      pontos.push({
        x: raio * Math.cos(angulo),
        y: raio * Math.sin(angulo),
        angulo,
        raio,
      });
    }
  });
  // Varre por ângulo: é isto que transforma "lista de partidos" em fatias.
  pontos.sort((a, b) => b.angulo - a.angulo || a.raio - b.raio);

  const entreArcos = arcos === 1 ? 0.5 : (1 - RAIO_INTERNO) / (arcos - 1);
  const noArcoMaisApertado = Math.min(
    ...raios.map((r, i) => (porArco[i] > 0 ? (Math.PI * r) / porArco[i] : Infinity)),
  );
  const raioDaBolinha = Math.min(entreArcos, noArcoMaisApertado, 0.16) * 0.42;
  return { pontos, raioDaBolinha };
}

type Props = {
  assentos: Assento[];
  /** Partido em destaque: os demais ficam apagados. */
  destaque?: number | null;
  onPassar?: (partido: number | null) => void;
  onClicar?: (partido: number) => void;
  /** Rótulo para leitor de tela. */
  rotulo: string;
  className?: string;
};

export function Hemiciclo({
  assentos, destaque, onPassar, onClicar, rotulo, className,
}: Props) {
  const { pontos, raioDaBolinha: rb } = posicoesDoHemiciclo(assentos.length);
  const margem = rb + 0.02;

  return (
    <svg
      viewBox={`${-1 - margem} ${-1 - margem} ${2 + 2 * margem} ${1 + 2 * margem}`}
      role="img"
      aria-label={rotulo}
      className={className}
      onMouseLeave={() => onPassar?.(null)}
    >
      {assentos.map((a, i) => {
        const p = pontos[i];
        const cor = a.partido == null ? "currentColor" : partyColor(a.partido);
        const apagado = destaque != null && a.partido !== destaque;
        const vaga = a.estado === "vaga";
        const parcial = a.estado === "parcial";
        return (
          <circle
            key={i}
            cx={p.x}
            cy={-p.y}
            // Contorno para dentro do raio: a bolinha vazada não fica maior que a cheia.
            r={vaga || parcial ? rb * 0.82 : rb}
            fill={vaga ? "none" : cor}
            fillOpacity={parcial ? 0.22 : 1}
            stroke={vaga || parcial ? cor : "rgba(255,255,255,0.35)"}
            strokeWidth={vaga || parcial ? rb * 0.36 : rb * 0.12}
            strokeOpacity={vaga ? 0.25 : 1}
            strokeDasharray={vaga ? `${rb * 0.5} ${rb * 0.5}` : undefined}
            opacity={apagado ? 0.14 : 1}
            style={{
              transition: "opacity 160ms",
              cursor: a.partido != null && onClicar ? "pointer" : "default",
            }}
            onMouseEnter={() => a.partido != null && onPassar?.(a.partido)}
            onClick={() => a.partido != null && onClicar?.(a.partido)}
          >
            <title>{a.titulo}</title>
          </circle>
        );
      })}
    </svg>
  );
}
