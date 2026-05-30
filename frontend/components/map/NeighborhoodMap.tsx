"use client";

/**
 * NeighborhoodMap — heatmap focado em um bairro especifico OU em todos.
 *
 * Usado em /dashboard/analises/bairros como painel lateral do mapa.
 * Centraliza no centroide do bairro quando o usuario clica num item da lista.
 */
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet.heat";
import { MapContainer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import type { HeatmapResponse } from "@/lib/types";
import { ThemedTileLayer } from "./ThemedTileLayer";

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

const DEFAULT_CENTER: [number, number] = [-21.7642, -43.3496]; // Juiz de Fora
const DEFAULT_ZOOM = 12;

type Props = {
  heatmap: HeatmapResponse | null;
  // Centroide do bairro selecionado (centraliza mapa + zoom in)
  focus?: { lat: number; lng: number } | null;
};

export default function NeighborhoodMap({ heatmap, focus }: Props) {
  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      scrollWheelZoom
      className="h-full w-full rounded-lg"
    >
      <ThemedTileLayer />
      {heatmap && <HeatLayer data={heatmap} />}
      {focus && <FocusController lat={focus.lat} lng={focus.lng} />}
    </MapContainer>
  );
}

function HeatLayer({ data }: { data: HeatmapResponse }) {
  const map = useMap();
  const layerRef = useRef<L.Layer | null>(null);

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }
    if (data.points.length === 0) return;

    const points: Array<[number, number, number]> = data.points.map((p) => [
      p.lat,
      p.lng,
      p.intensity,
    ]);

    const heat = L.heatLayer(points, {
      radius: 25,
      blur: 18,
      maxZoom: 17,
      max: 1.0,
      minOpacity: 0.3,
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

    // Auto-fit no primeiro render
    if (data.points.length > 0) {
      const bounds = L.latLngBounds(
        data.points.map((p) => [p.lat, p.lng] as [number, number]),
      );
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
    }

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [data, map]);

  return null;
}

function FocusController({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo([lat, lng], 15, { duration: 0.8 });
  }, [lat, lng, map]);
  return null;
}
