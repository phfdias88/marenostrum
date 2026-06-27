"use client";

/**
 * Mapa da Campanha — bolhas (CircleMarker) por grupo (bairro ou local de
 * votação). O raio cresce com a contagem de contatos/demandas. Importado
 * via next/dynamic({ssr:false}) — Leaflet acessa window no módulo.
 */
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { CircleMarker, MapContainer, Tooltip, useMap } from "react-leaflet";
import { useEffect } from "react";

import { ThemedTileLayer } from "./ThemedTileLayer";

export type MapGroup = {
  key: string;
  count: number;
  lat: number | null;
  lng: number | null;
};

const DEFAULT_CENTER: [number, number] = [-22.9, -43.2]; // RJ
const DEFAULT_ZOOM = 10;

// Leaflet em container flex mede errado no mount (tiles faltando no topo).
// invalidateSize após o layout assentar resolve.
function InvalidateOnMount() {
  const map = useMap();
  useEffect(() => {
    const t1 = setTimeout(() => map.invalidateSize(), 80);
    const t2 = setTimeout(() => map.invalidateSize(), 400);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [map]);
  return null;
}

// Ajusta o enquadramento às bolhas sempre que o conjunto muda.
function FitToGroups({ groups }: { groups: MapGroup[] }) {
  const map = useMap();
  const fp = groups.map((g) => `${g.lat},${g.lng}`).join("|");
  useEffect(() => {
    const pts = groups
      .filter((g) => g.lat != null && g.lng != null)
      .map((g) => [g.lat as number, g.lng as number] as [number, number]);
    // Espera o layout flex assentar, corrige o tamanho do mapa e SÓ ENTÃO
    // enquadra — senão o fitBounds calcula com o tamanho errado e sobra
    // fundo no topo (tiles fora do enquadramento).
    const id = setTimeout(() => {
      map.invalidateSize();
      if (!pts.length) return;
      // 1 ponto só: fitBounds degenera e não centraliza (o mapa ficava no
      // default do Rio mesmo com contato em Seropédica). setView resolve.
      if (pts.length === 1) {
        map.setView(pts[0], 13);
        return;
      }
      const b = L.latLngBounds(pts);
      if (b.isValid()) map.fitBounds(b, { padding: [40, 40], maxZoom: 14 });
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fp]);
  return null;
}

export default function CampaignMap({
  groups,
  metricLabel,
}: {
  groups: MapGroup[];
  metricLabel: string;
}) {
  const withCoords = groups.filter((g) => g.lat != null && g.lng != null);
  const max = Math.max(1, ...groups.map((g) => g.count));

  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      style={{ height: "100%", width: "100%", background: "#0b0b0c" }}
      scrollWheelZoom
      preferCanvas
    >
      <ThemedTileLayer />
      <InvalidateOnMount />
      <FitToGroups groups={withCoords} />
      {withCoords.map((g) => {
        // Raio entre 8 e 34px proporcional à raiz da contagem (área ∝ contagem).
        const r = 8 + 26 * Math.sqrt(g.count / max);
        return (
          <CircleMarker
            key={g.key}
            center={[g.lat as number, g.lng as number]}
            radius={r}
            pathOptions={{
              color: "#e8c879",
              fillColor: "#e8c879",
              fillOpacity: 0.45,
              weight: 1.5,
            }}
          >
            <Tooltip direction="top" offset={[0, -4]}>
              <span className="font-semibold">{g.key}</span>: {g.count}{" "}
              {metricLabel}
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
