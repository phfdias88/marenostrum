"use client";

/**
 * Mapa do Brasil com cada municipio pintado pela cor do partido vencedor.
 * CircleMarkers nos centroides (temos lat/lng dos municipios).
 */
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import type { TseWinnerMapPoint } from "@/lib/types";

const numberFmt = new Intl.NumberFormat("pt-BR");

// Cor por numero de partido (mesma paleta do PartyLogo)
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

export default function WinnersMap({ points }: { points: TseWinnerMapPoint[] }) {
  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={4}
      scrollWheelZoom
      preferCanvas
      className="h-full w-full"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {points.map((p) => {
        const color = PARTY_COLOR[p.party_number] ?? "#888";
        return (
          <CircleMarker
            key={p.municipality_id}
            center={[p.lat, p.lng]}
            radius={4}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.85,
              weight: 0.5,
            }}
          >
            <Popup>
              <div className="text-sm">
                <p className="font-semibold">
                  {p.name}/{p.state}
                </p>
                <p>
                  <strong style={{ color }}>{p.party_abbreviation}</strong> —{" "}
                  {p.winner_name}
                </p>
                <p className="text-xs">{numberFmt.format(p.votes)} votos</p>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
