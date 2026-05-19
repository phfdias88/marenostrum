"use client";

/**
 * CandidateVoteMap — exibe a distribuicao de votos de UM candidato TSE
 * pelo Brasil, com bolhas dimensionadas pelo total de votos por municipio.
 *
 * Para prefeitos/vereadores tipicamente sera 1 ponto (cidade onde ele
 * concorreu). Para deputados/senadores (datasets futuros) brilhara mais.
 *
 * Decisao: bolhas (CircleMarker) ao inves de heatmap pra mostrar valores
 * individuais com tooltip. Tamanho do raio = sqrt(votos / maxVotos) * 30.
 */
import { useMemo } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect } from "react";

import type { TseCandidateResults } from "@/lib/types";

const numberFmt = new Intl.NumberFormat("pt-BR");

const DEFAULT_CENTER: [number, number] = [-14.5, -52.0]; // Brasil
const DEFAULT_ZOOM = 4;

export default function CandidateVoteMap({
  results,
}: {
  results: TseCandidateResults;
}) {
  // So entram os com coord
  const withCoords = useMemo(
    () =>
      results.results.filter(
        (r) =>
          r.municipality.latitude != null && r.municipality.longitude != null,
      ),
    [results],
  );

  const missingCoords = results.results.length - withCoords.length;
  const maxVotes = withCoords[0]?.votes ?? 1;

  return (
    <div className="h-full w-full flex flex-col">
      <div className="flex-1 relative">
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={DEFAULT_ZOOM}
          scrollWheelZoom
          className="h-full w-full"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {withCoords.map((r) => {
            // raio em pixels: sqrt scale pra evitar bolhas gigantes
            const pct = r.votes / maxVotes;
            const radius = Math.max(6, Math.sqrt(pct) * 30);
            // cor: verde -> amarelo -> laranja -> vermelho por intensidade
            const fillColor =
              pct > 0.7
                ? "#dc2626"
                : pct > 0.4
                  ? "#f97316"
                  : pct > 0.15
                    ? "#f0ad4e"
                    : "#5cb85c";
            return (
              <CircleMarker
                key={r.municipality.id}
                center={[
                  r.municipality.latitude as number,
                  r.municipality.longitude as number,
                ]}
                radius={radius}
                pathOptions={{
                  color: fillColor,
                  fillColor,
                  fillOpacity: 0.55,
                  weight: 1.5,
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <p className="font-semibold">
                      {r.municipality.name} / {r.municipality.state}
                    </p>
                    <p className="text-primary font-bold text-base">
                      {numberFmt.format(r.votes)} votos
                    </p>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}

          <AutoFit
            points={withCoords.map(
              (r) =>
                [
                  r.municipality.latitude as number,
                  r.municipality.longitude as number,
                ] as [number, number],
            )}
          />
        </MapContainer>
      </div>

      <div className="px-3 py-2 text-xs text-muted-foreground bg-card border-t border-border flex items-center justify-between gap-2 flex-wrap">
        <span>
          {numberFmt.format(withCoords.length)} município(s) plotado(s)
          {missingCoords > 0 && (
            <span className="ml-2 text-amber-500">
              · {numberFmt.format(missingCoords)} sem coordenadas
            </span>
          )}
        </span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-emerald-500" />
            poucos
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-amber-500" />
            médios
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-orange-500" />
            muitos
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-red-600" />
            top
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
      map.setView(points[0], 11);
      return;
    }
    const bounds = L.latLngBounds(points);
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
  }, [points, map]);
  return null;
}
