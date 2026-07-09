"use client";

/**
 * Mapa do Brasil com cada municipio pintado pela cor do partido vencedor.
 *
 * Melhorias:
 *  - Tile tematico (CartoDB Dark/Voyager) ao inves do OSM cru.
 *  - Tooltip on hover (sem precisar clicar).
 *  - Suporte a `highlightedParty`: quando setado, dim os outros e destaca
 *    so os municipios do partido escolhido.
 *  - Imperative pan/zoom via `focusRequest` (chips UF na pagina pai).
 *
 * PERFORMANCE: os pontos (ate ~5570 municipios) sao desenhados como UMA camada
 * imperativa de L.circleMarker no renderer canvas — NAO como 5570 componentes
 * React <CircleMarker> + 5570 portals de <Tooltip>. O realce por partido
 * re-estiliza os marcadores IN-PLACE (setStyle), sem reconciliar/recriar nada.
 */
import { useEffect, useRef } from "react";
import L from "leaflet";
import { MapContainer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { partyColor } from "@/lib/partyColors";
import type { TseWinnerMapPoint } from "@/lib/types";
import { ThemedTileLayer } from "./ThemedTileLayer";

const numberFmt = new Intl.NumberFormat("pt-BR");

const DEFAULT_CENTER: [number, number] = [-14.5, -52.0];

// Estilo de um ponto em funcao do realce atual (dourado nos do partido, dim nos outros).
function styleFor(party: number, hl: number | null | undefined) {
  const color = partyColor(party);
  const dimmed = hl != null && party !== hl;
  const active = hl != null && party === hl;
  return {
    radius: active ? 6 : dimmed ? 2.5 : 4,
    color,
    fillColor: color,
    fillOpacity: dimmed ? 0.18 : 0.85,
    weight: active ? 1 : 0.5,
  };
}

type Props = {
  points: TseWinnerMapPoint[];
  /** Quando setado, destaca so os municipios desse partido. */
  highlightedParty?: number | null;
  /** Pedido externo de pan/zoom (lat, lng, zoom). */
  focusRequest?: { lat: number; lng: number; zoom: number; key: number } | null;
};

export default function WinnersMap({ points, highlightedParty, focusRequest }: Props) {
  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={4}
      scrollWheelZoom
      preferCanvas
      className="h-full w-full"
    >
      <ThemedTileLayer />
      <MarkersLayer points={points} highlightedParty={highlightedParty} />
      <FocusController req={focusRequest} />
    </MapContainer>
  );
}

// Camada imperativa: 1 L.circleMarker por ponto num layerGroup, desenhado no
// canvas do mapa (preferCanvas). Reconstrói so quando `points` muda; o realce
// re-estiliza in-place sem recriar (le o highlight via ref pra nao rebuildar).
function MarkersLayer({
  points,
  highlightedParty,
}: {
  points: TseWinnerMapPoint[];
  highlightedParty?: number | null;
}) {
  const map = useMap();
  const markersRef = useRef<Array<{ marker: L.CircleMarker; party: number }>>([]);
  const hlRef = useRef(highlightedParty);
  hlRef.current = highlightedParty;

  useEffect(() => {
    const group = L.layerGroup().addTo(map);
    const built: Array<{ marker: L.CircleMarker; party: number }> = [];
    for (const p of points) {
      const { radius, ...path } = styleFor(p.party_number, hlRef.current);
      const marker = L.circleMarker([p.lat, p.lng], { radius, ...path });
      const color = partyColor(p.party_number);
      marker.bindTooltip(
        `${p.name}/${p.state} · <b style="color:${color}">${p.party_abbreviation}</b> · ${numberFmt.format(p.votes)}`,
        { direction: "top", offset: [0, -4], className: "mn-tip", opacity: 1 },
      );
      marker.addTo(group);
      built.push({ marker, party: p.party_number });
    }
    markersRef.current = built;
    return () => {
      group.remove();
      markersRef.current = [];
    };
  }, [points, map]);

  useEffect(() => {
    for (const { marker, party } of markersRef.current) {
      const { radius, ...path } = styleFor(party, highlightedParty);
      marker.setRadius(radius);
      marker.setStyle(path);
    }
  }, [highlightedParty]);

  return null;
}

function FocusController({
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
