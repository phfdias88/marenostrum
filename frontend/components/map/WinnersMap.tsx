"use client";

/**
 * Mapa do Brasil com cada municipio pintado pela cor do partido vencedor.
 *
 * Melhorias:
 *  - Tile tematico (CartoDB Dark/Voyager) ao inves do OSM cru.
 *  - Top 3 municipios (por votos) ganham marker pulsante dourado por cima.
 *  - Tooltip on hover (sem precisar clicar).
 *  - Suporte a `highlightedParty`: quando setado, dim os outros e destaca
 *    so os municipios do partido escolhido.
 *  - Imperative pan/zoom via `focusRequest` (chips UF na pagina pai).
 */
import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { CircleMarker, MapContainer, Marker, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import type { TseWinnerMapPoint } from "@/lib/types";
import { ThemedTileLayer } from "./ThemedTileLayer";

const numberFmt = new Intl.NumberFormat("pt-BR");

const PARTY_COLOR: Record<number, string> = {
  10: "#0050a0", 11: "#ff8c00", 12: "#c41a1a", 13: "#e30613", 14: "#0099cc",
  15: "#2d6f30", 16: "#a31a1a", 17: "#ffcd1a", 18: "#7fbc41", 19: "#16a085",
  20: "#1f5fa6", 22: "#0a2a7d", 23: "#3f51b5", 25: "#0050a0", 27: "#27ae60",
  28: "#e91e63", 30: "#ff5a00", 33: "#0d47a1", 35: "#c97312", 36: "#7b1fa2",
  40: "#d81b60", 43: "#1e8a3c", 44: "#ed9b00", 45: "#005faa", 50: "#dc143c",
  51: "#1c8537", 55: "#00a99d", 65: "#cc0000", 70: "#d35400", 77: "#673ab7",
  80: "#6b6b6b", 90: "#37474f",
};

const DEFAULT_CENTER: [number, number] = [-14.5, -52.0];

const PULSE_ICON = L.divIcon({
  className: "mn-pulse-marker",
  html: '<div class="mn-pulse-wrap"><div class="mn-pulse-ring"></div><div class="mn-pulse-dot"></div></div>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

type Props = {
  points: TseWinnerMapPoint[];
  /** Quando setado, destaca so os municipios desse partido. */
  highlightedParty?: number | null;
  /** Pedido externo de pan/zoom (lat, lng, zoom). */
  focusRequest?: { lat: number; lng: number; zoom: number; key: number } | null;
};

export default function WinnersMap({ points, highlightedParty, focusRequest }: Props) {
  // Top 3 municipios por votos pra pulsar
  const top3 = useMemo(
    () => [...points].sort((a, b) => b.votes - a.votes).slice(0, 3),
    [points],
  );

  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={4}
      scrollWheelZoom
      preferCanvas
      className="h-full w-full"
    >
      <ThemedTileLayer />
      {points.map((p) => {
        const color = PARTY_COLOR[p.party_number] ?? "#888";
        const dimmed =
          highlightedParty != null && p.party_number !== highlightedParty;
        const active =
          highlightedParty != null && p.party_number === highlightedParty;
        return (
          <CircleMarker
            key={p.municipality_id}
            center={[p.lat, p.lng]}
            radius={active ? 6 : dimmed ? 2.5 : 4}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: dimmed ? 0.18 : 0.85,
              weight: active ? 1 : 0.5,
            }}
          >
            <Tooltip
              direction="top"
              offset={[0, -4]}
              className="mn-tip"
              opacity={1}
            >
              <span>
                {p.name}/{p.state} · <b style={{ color }}>{p.party_abbreviation}</b>{" "}
                · {numberFmt.format(p.votes)}
              </span>
            </Tooltip>
          </CircleMarker>
        );
      })}

      {/* Pulse dourado nos top 3 — chama atencao */}
      {top3.map((p) => (
        <Marker
          key={`pulse-${p.municipality_id}`}
          position={[p.lat, p.lng]}
          icon={PULSE_ICON}
          interactive={false}
          keyboard={false}
        />
      ))}

      <FocusController req={focusRequest} />
    </MapContainer>
  );
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
