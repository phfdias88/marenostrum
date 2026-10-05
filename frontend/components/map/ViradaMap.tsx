"use client";

/**
 * Mapa da virada: o que mudou em cada município entre duas eleições.
 *
 * O mapa partidário responde "quem ganhou aqui". Este responde a pergunta que
 * vem logo depois e que ele não mostra: "isso é novidade ou sempre foi assim?".
 * Município que manteve o partido fica discreto; o que VIROU salta — maior,
 * opaco e com contorno, na cor de quem passou a ganhar.
 *
 * Mesma técnica do WinnersMap: uma camada imperativa de L.circleMarker no
 * canvas, reestilizada in-place no realce. São ~5.570 pontos; como componentes
 * React seriam 5.570 portais de tooltip.
 */
import { useEffect, useRef } from "react";
import L from "leaflet";
import { MapContainer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { partyColor } from "@/lib/partyColors";
import type { TseViradaPoint as ViradaPoint } from "@/lib/types";
import { useMapLayout } from "@/lib/useMapLayout";
import { ThemedTileLayer } from "./ThemedTileLayer";

const numberFmt = new Intl.NumberFormat("pt-BR");

const DEFAULT_CENTER: [number, number] = [-14.5, -52.0];

/** O que destacar: uma transição específica, ou só quem virou / só quem manteve. */
export type ViradaFiltro =
  | { tipo: "transicao"; chave: string }
  | { tipo: "viraram" }
  | { tipo: "mantiveram" };

function casa(p: ViradaPoint, f: ViradaFiltro): boolean {
  if (f.tipo === "transicao") return p.transicao === f.chave;
  return f.tipo === "viraram" ? p.virou : !p.virou;
}

// O contorno é o que faz o ponto "saltar": precisa contrastar com o FUNDO do
// mapa, que o usuário escolhe. Branco some no mapa claro (o padrão).
const ANEL_NO_CLARO = "#0f172a";
const ANEL_NO_ESCURO = "#ffffff";

function styleFor(p: ViradaPoint, f: ViradaFiltro | null | undefined, anel: string) {
  const color = partyColor(p.depois.party_number);
  // Com um filtro ligado, só o que casa com ele aparece forte.
  if (f) {
    const active = casa(p, f);
    return {
      radius: active ? 5.5 : 2.5,
      color: active ? anel : color,
      fillColor: color,
      fillOpacity: active ? 0.95 : 0.1,
      weight: active ? 1.1 : 0.3,
    };
  }
  return p.virou
    ? { radius: 5, color: anel, fillColor: color, fillOpacity: 0.95, weight: 1.1 }
    : { radius: 3, color, fillColor: color, fillOpacity: 0.3, weight: 0.4 };
}

type Props = {
  points: ViradaPoint[];
  anoAntes: number;
  anoDepois: number;
  highlighted?: ViradaFiltro | null;
  focusRequest?: { lat: number; lng: number; zoom: number; key: number } | null;
};

export default function ViradaMap({
  points, anoAntes, anoDepois, highlighted, focusRequest,
}: Props) {
  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={4}
      scrollWheelZoom
      preferCanvas
      className="h-full w-full"
    >
      <ThemedTileLayer />
      <Camada
        points={points}
        anoAntes={anoAntes}
        anoDepois={anoDepois}
        highlighted={highlighted}
      />
      <Foco req={focusRequest} />
    </MapContainer>
  );
}

function Camada({
  points, anoAntes, anoDepois, highlighted,
}: {
  points: ViradaPoint[];
  anoAntes: number;
  anoDepois: number;
  highlighted?: ViradaFiltro | null;
}) {
  const map = useMap();
  const [layout] = useMapLayout();
  const anel = layout === "light" ? ANEL_NO_CLARO : ANEL_NO_ESCURO;
  const ref = useRef<Array<{ marker: L.CircleMarker; p: ViradaPoint }>>([]);
  // Lidos por ref na construção: mudar o destaque ou o fundo reestiliza os
  // pontos no lugar (efeito abaixo), sem recriar os 5.570 marcadores.
  const hlRef = useRef(highlighted);
  hlRef.current = highlighted;
  const anelRef = useRef(anel);
  anelRef.current = anel;

  useEffect(() => {
    const group = L.layerGroup().addTo(map);
    const built: Array<{ marker: L.CircleMarker; p: ViradaPoint }> = [];
    // Quem manteve vai primeiro: assim os que viraram são desenhados POR CIMA
    // e não ficam escondidos atrás de um vizinho nas regiões densas.
    const ordenados = [...points].sort((a, b) => Number(a.virou) - Number(b.virou));
    // O nome vem do TSE e vai para dentro de HTML (bindTooltip): escapar.
    const esc = (s: string) =>
      s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
    for (const p of ordenados) {
      const { radius, ...path } = styleFor(p, hlRef.current, anelRef.current);
      const marker = L.circleMarker([p.lat, p.lng], { radius, ...path });
      const cA = partyColor(p.antes.party_number);
      const cD = partyColor(p.depois.party_number);
      const titulo = p.virou ? "virou" : "manteve";
      marker.bindTooltip(
        `<b>${esc(p.name)}/${p.state}</b> · ${titulo}<br/>` +
          `${anoAntes}: <b style="color:${cA}">${esc(p.antes.party_abbreviation)}</b> ` +
          `${esc(p.antes.winner_name)} · ${numberFmt.format(p.antes.votes)}<br/>` +
          `${anoDepois}: <b style="color:${cD}">${esc(p.depois.party_abbreviation)}</b> ` +
          `${esc(p.depois.winner_name)} · ${numberFmt.format(p.depois.votes)}`,
        { direction: "top", offset: [0, -4], className: "mn-tip", opacity: 1 },
      );
      marker.addTo(group);
      built.push({ marker, p });
    }
    ref.current = built;
    return () => {
      group.remove();
      ref.current = [];
    };
  }, [points, map, anoAntes, anoDepois]);

  useEffect(() => {
    for (const { marker, p } of ref.current) {
      const { radius, ...path } = styleFor(p, highlighted, anel);
      marker.setRadius(radius);
      marker.setStyle(path);
    }
  }, [highlighted, anel]);

  return null;
}

function Foco({
  req,
}: {
  req?: { lat: number; lng: number; zoom: number; key: number } | null;
}) {
  const map = useMap();
  useEffect(() => {
    if (!req) return;
    map.flyTo([req.lat, req.lng], req.zoom, { duration: 0.7 });
  }, [req?.key, map]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}
