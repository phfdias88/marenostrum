"use client";

/**
 * Mapa da Campanha — bolhas (CircleMarker) por grupo (bairro ou local de
 * votação). O raio cresce com a contagem de contatos/demandas. Importado
 * via next/dynamic({ssr:false}) — Leaflet acessa window no módulo.
 */
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import "leaflet.heat"; // side-effect — registra L.heatLayer
import { CircleMarker, MapContainer, Tooltip, useMap } from "react-leaflet";
import { useEffect, useRef } from "react";

import { ThemedTileLayer } from "./ThemedTileLayer";

// leaflet.heat não tem tipos — declara o mínimo que usamos.
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
      // animate:false é ESSENCIAL — o setView/fitBounds animado é engolido
      // durante o churn de init do mapa (invalidateSize), deixando o mapa no
      // centro default. Sem animação, aplica na hora.
      // 1 ponto só: fitBounds degenera; setView direto.
      if (pts.length === 1) {
        map.setView(pts[0], 13, { animate: false });
        return;
      }
      const b = L.latLngBounds(pts);
      if (b.isValid()) {
        map.fitBounds(b, { padding: [40, 40], maxZoom: 14, animate: false });
      }
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fp]);
  return null;
}

// Heatmap (leaflet.heat) — densidade de contatos/demandas. Alterna com as
// bolhas. Intensidade = raiz(count/max) com piso, pra 1 contato ainda aparecer.
function HeatLayer({ groups, max }: { groups: MapGroup[]; max: number }) {
  const map = useMap();
  const layerRef = useRef<L.Layer | null>(null);
  const fp = groups.map((g) => `${g.lat},${g.lng}:${g.count}`).join("|");
  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }
    const pts = groups
      .filter((g) => g.lat != null && g.lng != null)
      .map(
        (g) =>
          [g.lat as number, g.lng as number, Math.max(0.15, Math.sqrt(g.count / max))] as [
            number,
            number,
            number,
          ],
      );
    if (!pts.length) return;
    // invalidateSize antes (mesmo motivo do FitToGroups) e enquadra nos pontos.
    const t = setTimeout(() => {
      map.invalidateSize();
      const heat = L.heatLayer(pts, {
        radius: 28,
        blur: 20,
        maxZoom: 16,
        max: 1.0,
        minOpacity: 0.35,
        gradient: {
          0.0: "#1e6fd9",
          0.3: "#5cb85c",
          0.6: "#f0ad4e",
          0.85: "#f97316",
          1.0: "#dc2626",
        },
      });
      heat.addTo(map);
      layerRef.current = heat;
      if (pts.length === 1) {
        map.setView([pts[0][0], pts[0][1]], 13, { animate: false });
      } else {
        const b = L.latLngBounds(pts.map((p) => [p[0], p[1]] as [number, number]));
        if (b.isValid()) map.fitBounds(b, { padding: [40, 40], maxZoom: 14, animate: false });
      }
    }, 300);
    return () => {
      clearTimeout(t);
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fp, max]);
  return null;
}

export default function CampaignMap({
  groups,
  metricLabel,
  showHeatmap = false,
}: {
  groups: MapGroup[];
  metricLabel: string;
  showHeatmap?: boolean;
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
      {showHeatmap ? (
        <HeatLayer groups={withCoords} max={max} />
      ) : (
        <FitToGroups groups={withCoords} />
      )}
      {!showHeatmap &&
        withCoords.map((g) => {
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
