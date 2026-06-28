"use client";

/**
 * CandidateNeighborhoodMap — bolhas por bairro pra um candidato.
 *
 * Diferente do CandidateVoteMap (que mostra por municipio), aqui usa
 * o endpoint /candidates/{id}/by-neighborhood com filtro por municipio.
 * Cada bolha = centroide do bairro, raio = sqrt(votos/max) * 35.
 */
import { useEffect, useMemo } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Popup,
  Tooltip,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

import type { TseCandidateByNeighborhoodResponse } from "@/lib/types";
import { ThemedTileLayer } from "./ThemedTileLayer";

const numberFmt = new Intl.NumberFormat("pt-BR");
const DEFAULT_CENTER: [number, number] = [-14.5, -52.0];

export default function CandidateNeighborhoodMap({
  data,
}: {
  data: TseCandidateByNeighborhoodResponse;
}) {
  const withCoords = useMemo(
    () => data.items.filter((i) => i.avg_lat != null && i.avg_lng != null),
    [data.items],
  );
  const missing = data.items.length - withCoords.length;
  const maxVotes = withCoords[0]?.votes ?? 1;

  return (
    <div className="h-full w-full flex flex-col">
      <div className="flex-1 relative">
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={4}
          scrollWheelZoom
          preferCanvas
          className="h-full w-full"
        >
          <ThemedTileLayer />

          {withCoords.map((r) => {
            const pct = r.votes / maxVotes;
            const radius = Math.max(8, Math.sqrt(pct) * 35);
            const color =
              pct > 0.7
                ? "#dc2626"
                : pct > 0.4
                  ? "#f97316"
                  : pct > 0.15
                    ? "#f0ad4e"
                    : "#5cb85c";
            return (
              <CircleMarker
                key={r.neighborhood}
                center={[r.avg_lat as number, r.avg_lng as number]}
                radius={radius}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.55,
                  weight: 1.5,
                }}
              >
                <Tooltip direction="top" offset={[0, -4]} className="mn-tip" opacity={1}>
                  <span>
                    {r.neighborhood} · <b>{numberFmt.format(r.votes)}</b>
                  </span>
                </Tooltip>
                <Popup>
                  <div className="text-sm">
                    <p className="font-semibold">{r.neighborhood}</p>
                    <p className="text-primary font-bold text-base">
                      {numberFmt.format(r.votes)} votos
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {numberFmt.format(r.places_count)} local(is)
                      {r.electors_total > 0 && (
                        <>
                          {" · "}
                          {numberFmt.format(r.electors_total)} eleitores
                        </>
                      )}
                    </p>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}

          <AutoFit
            points={withCoords.map(
              (r) => [r.avg_lat as number, r.avg_lng as number] as [number, number],
            )}
          />
        </MapContainer>
      </div>

      <div className="px-3 py-2 text-xs text-muted-foreground bg-card border-t border-border flex items-center justify-between gap-2 flex-wrap">
        <span>
          {numberFmt.format(withCoords.length)} bairro(s) plotado(s)
          {missing > 0 && (
            <span className="ml-2 text-amber-500">
              · {numberFmt.format(missing)} sem coordenadas
            </span>
          )}
        </span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-emerald-500" /> poucos
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-amber-500" /> médios
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-orange-500" /> muitos
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-red-600" /> top
          </span>
        </span>
      </div>
    </div>
  );
}

function AutoFit({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 14, { animate: false });
      return;
    }
    const bounds = L.latLngBounds(points);
    // animate:false — senão o enquadramento é engolido na init do mapa (gotcha).
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14, animate: false });
  }, [points, map]);
  return null;
}
