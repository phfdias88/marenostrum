"use client";

/**
 * CandidateNeighborhoodMap — bolhas por bairro pra um candidato.
 *
 * Diferente do CandidateVoteMap (que mostra por municipio), aqui usa
 * o endpoint /candidates/{id}/by-neighborhood com filtro por municipio.
 * Cada bolha = centroide do bairro, raio = sqrt(votos/max) * 35.
 */
import { useEffect, useMemo, useRef } from "react";
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

export type VotingPlacePoint = {
  id: string;
  name: string;
  neighborhood: string | null;
  lat: number;
  lng: number;
  electors: number | null;
  /** Município do local — desambigua escolas homônimas ("Nome (Município)"). */
  municipality?: string | null;
};

// Rótulo composto "Bairro (Município)" — regra de exibição do PO: deputado
// recebe voto no estado inteiro e todo município tem um "Centro"; sem o
// município junto, bairros homônimos viram ruído.
function nbLabel(r: { neighborhood: string; municipality_name?: string | null }): string {
  return r.municipality_name
    ? `${r.neighborhood} (${r.municipality_name})`
    : r.neighborhood;
}

export default function CandidateNeighborhoodMap({
  data,
  votingPlaces,
}: {
  data: TseCandidateByNeighborhoodResponse;
  /** Camada opcional de locais de votação (marcadores discretos). */
  votingPlaces?: VotingPlacePoint[];
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
                // Chave COMPOSTA: só o bairro colidia em homônimos estaduais
                // (todo "Centro" do estado = mesma key React).
                key={`${r.municipality_id ?? ""}-${r.neighborhood}`}
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
                    {nbLabel(r)} · <b>{numberFmt.format(r.votes)}</b>
                  </span>
                </Tooltip>
                <Popup>
                  <div className="text-sm">
                    <p className="font-semibold">{nbLabel(r)}</p>
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

          {/* Camada de locais de votação (marcadores pequenos, azuis) —
              IMPERATIVA: até 3000 locais viravam ~9000 mounts React
              (CircleMarker+Tooltip+Popup) e o rebuild por tecla do filtro
              pesava no mobile. 1 L.layerGroup em canvas resolve. */}
          {votingPlaces && votingPlaces.length > 0 && (
            <PlacesLayer places={votingPlaces} />
          )}

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
          {votingPlaces && votingPlaces.length > 0 && (
            <span className="ml-2 inline-flex items-center gap-1 text-blue-500">
              · <span className="w-2 h-2 rounded-full bg-blue-500" />
              {numberFmt.format(votingPlaces.length)} locais de votação
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
  // Assinatura por VALOR: os filtros do modal re-renderizam o mapa com um
  // array NOVO (mesma coordenada) a cada tecla/fetch — refit por identidade
  // resetava o pan/zoom do usuário toda hora. Só refita quando o CONJUNTO
  // de pontos muda de fato.
  const sig = points.map((p) => p.join(",")).join("|");
  const ptsRef = useRef(points);
  ptsRef.current = points;
  useEffect(() => {
    const pts = ptsRef.current;
    if (pts.length === 0) return;
    if (pts.length === 1) {
      map.setView(pts[0], 14, { animate: false });
      return;
    }
    const bounds = L.latLngBounds(pts);
    // animate:false — senão o enquadramento é engolido na init do mapa (gotcha).
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14, animate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, map]);
  return null;
}

// Escapa HTML pra bindTooltip/bindPopup (strings cruas do TSE).
function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Locais como UMA camada imperativa (mesmo padrão do BubblesLayer do
// CandidateVoteMap): canvas, sem mount React por marcador. Rótulos mantêm a
// desambiguação "Nome (Município)".
function PlacesLayer({ places }: { places: VotingPlacePoint[] }) {
  const map = useMap();
  useEffect(() => {
    if (places.length === 0) return;
    const group = L.layerGroup();
    for (const vp of places) {
      const m = L.circleMarker([vp.lat, vp.lng], {
        radius: 3.5,
        color: "#1d4ed8",
        fillColor: "#3b82f6",
        fillOpacity: 0.9,
        weight: 1,
      });
      const muni = vp.municipality ? ` (${esc(vp.municipality)})` : "";
      const nb = vp.neighborhood ? ` · ${esc(vp.neighborhood)}` : "";
      m.bindTooltip(`📍 ${esc(vp.name)}${muni}${nb}`, {
        direction: "top",
        offset: [0, -2],
        className: "mn-tip",
        opacity: 1,
      });
      m.bindPopup(
        `<div class="text-sm"><p class="font-semibold">${esc(vp.name)}${muni}</p>` +
          (vp.neighborhood
            ? `<p class="text-xs text-muted-foreground">${esc(vp.neighborhood)}</p>`
            : "") +
          (vp.electors != null && vp.electors > 0
            ? `<p class="text-xs text-muted-foreground">${numberFmt.format(vp.electors)} eleitores</p>`
            : "") +
          "</div>",
      );
      m.addTo(group);
    }
    group.addTo(map);
    return () => {
      map.removeLayer(group);
    };
  }, [places, map]);
  return null;
}
