"use client";

/**
 * CandidateVoteMap — distribuicao de votos de UM candidato pelo Brasil.
 *
 * Melhorias:
 *  - Tile tematico (CartoDB Dark/Voyager).
 *  - Toggle bolhas <-> heatmap (leaflet.heat).
 *  - Top 3 cidades pulsam em dourado.
 *  - Tooltip on hover (nao precisa clicar).
 *  - Overlay flutuante com top 3 cidades + total.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet.heat";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Tooltip,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { Flame, MapPin } from "lucide-react";

import type { TseCandidateResults } from "@/lib/types";
import { ThemedTileLayer } from "./ThemedTileLayer";

const numberFmt = new Intl.NumberFormat("pt-BR");

const DEFAULT_CENTER: [number, number] = [-14.5, -52.0];
const DEFAULT_ZOOM = 4;

const PULSE_ICON = L.divIcon({
  className: "mn-pulse-marker",
  html: '<div class="mn-pulse-wrap"><div class="mn-pulse-ring"></div><div class="mn-pulse-dot"></div></div>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

declare module "leaflet" {
  function heatLayer(
    points: Array<[number, number, number]>,
    options?: {
      radius?: number;
      blur?: number;
      maxZoom?: number;
      max?: number;
      minOpacity?: number;
      gradient?: Record<number, string>;
    },
  ): L.Layer;
}

type Mode = "bubbles" | "heat";

export default function CandidateVoteMap({
  results,
}: {
  results: TseCandidateResults;
}) {
  const [mode, setMode] = useState<Mode>("bubbles");
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
  const top3 = useMemo(() => withCoords.slice(0, 3), [withCoords]);
  const totalVotes = withCoords.reduce((s, r) => s + r.votes, 0);

  return (
    <div className="h-full w-full flex flex-col">
      <div className="flex-1 relative">
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={DEFAULT_ZOOM}
          scrollWheelZoom
          preferCanvas
          className="h-full w-full"
        >
          <ThemedTileLayer />

          {mode === "bubbles" &&
            withCoords.map((r) => {
              const pct = r.votes / maxVotes;
              const radius = Math.max(6, Math.sqrt(pct) * 30);
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
                  <Tooltip direction="top" offset={[0, -4]} className="mn-tip" opacity={1}>
                    <span>
                      {r.municipality.name}/{r.municipality.state} ·{" "}
                      <b>{numberFmt.format(r.votes)}</b>
                    </span>
                  </Tooltip>
                </CircleMarker>
              );
            })}

          {mode === "heat" && <HeatLayer points={withCoords} maxVotes={maxVotes} />}

          {/* Pulse dourado nos top 3 */}
          {top3.map((r) => (
            <Marker
              key={`pulse-${r.municipality.id}`}
              position={[
                r.municipality.latitude as number,
                r.municipality.longitude as number,
              ]}
              icon={PULSE_ICON}
              interactive={false}
              keyboard={false}
            />
          ))}

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

        {/* Toggle modo (top-right) */}
        <div className="absolute top-3 right-3 z-[400] flex bg-card/80 backdrop-blur border border-border rounded-lg p-1 text-xs">
          <button
            onClick={() => setMode("bubbles")}
            className={
              "px-2.5 py-1 rounded inline-flex items-center gap-1 transition-colors " +
              (mode === "bubbles"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            <MapPin className="w-3 h-3" /> Bolhas
          </button>
          <button
            onClick={() => setMode("heat")}
            className={
              "px-2.5 py-1 rounded inline-flex items-center gap-1 transition-colors " +
              (mode === "heat"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            <Flame className="w-3 h-3" /> Heatmap
          </button>
        </div>

        {/* Overlay top 3 (top-left) */}
        {top3.length > 0 && (
          <div className="absolute top-3 left-3 z-[400] mn-glass mn-slide-in rounded-xl px-4 py-3 max-w-xs">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Top cidades · {numberFmt.format(totalVotes)} votos
            </p>
            <ol className="mt-2 space-y-1.5">
              {top3.map((r, i) => (
                <li key={r.municipality.id} className="flex items-center gap-2 text-sm">
                  <span
                    className={
                      "w-5 h-5 grid place-items-center rounded-full text-[10px] font-bold " +
                      (i === 0
                        ? "bg-primary text-primary-foreground"
                        : "bg-primary/20 text-primary")
                    }
                  >
                    {i + 1}
                  </span>
                  <span className="flex-1 truncate font-medium">
                    {r.municipality.name}
                    <span className="text-muted-foreground">/{r.municipality.state}</span>
                  </span>
                  <span className="tabular-nums font-mono text-xs">
                    {numberFmt.format(r.votes)}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
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
        {mode === "bubbles" && (
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
        )}
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

function HeatLayer({
  points,
  maxVotes,
}: {
  points: { municipality: { latitude: number | null; longitude: number | null }; votes: number }[];
  maxVotes: number;
}) {
  const map = useMap();
  const ref = useRef<L.Layer | null>(null);

  useEffect(() => {
    if (ref.current) {
      map.removeLayer(ref.current);
      ref.current = null;
    }
    if (points.length === 0) return;
    const heat = L.heatLayer(
      points.map((p) => [
        p.municipality.latitude as number,
        p.municipality.longitude as number,
        p.votes / maxVotes,
      ]),
      {
        radius: 28,
        blur: 22,
        maxZoom: 14,
        max: 1.0,
        minOpacity: 0.35,
        // Gradiente dourado -> calor
        gradient: {
          0.0: "#0d4a6e",
          0.3: "#5cb85c",
          0.55: "#f0ad4e",
          0.78: "#f97316",
          1.0: "#dc2626",
        },
      },
    );
    heat.addTo(map);
    ref.current = heat;
    return () => {
      if (ref.current) {
        map.removeLayer(ref.current);
        ref.current = null;
      }
    };
  }, [points, maxVotes, map]);

  return null;
}
