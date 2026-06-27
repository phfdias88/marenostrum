"use client";

/**
 * Mini-mapa pra MARCAR uma coordenada com o clique. Usado no cadastro de
 * contato quando o bairro está fora da base (ex: Seropédica / "KM 32") e
 * precisamos da localização exata.
 *
 * Importado via next/dynamic({ssr:false}) — Leaflet acessa window no módulo.
 */
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import { MapContainer, Marker, useMap, useMapEvents } from "react-leaflet";

import { ThemedTileLayer } from "./ThemedTileLayer";

const pinIcon = L.divIcon({
  className: "mn-marker",
  html: `
    <svg width="28" height="36" viewBox="0 0 28 36" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 0C6.27 0 0 6.27 0 14c0 9.5 14 22 14 22s14-12.5 14-22C28 6.27 21.73 0 14 0z"
            fill="hsl(212, 76%, 48%)" stroke="white" stroke-width="2"/>
      <circle cx="14" cy="14" r="5" fill="white"/>
    </svg>
  `,
  iconSize: [28, 36],
  iconAnchor: [14, 36],
});

function ClickCapture({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

// O `center` (centro do município) costuma chegar via fetch DEPOIS que o mapa
// montou (que abre no centro da UF como fallback). react-leaflet não recentra
// sozinho quando a prop muda — então recentramos aqui, mas só enquanto NÃO há
// ponto marcado (pra não puxar o mapa de volta depois que o usuário clicou).
function RecenterOnChange({
  center,
  zoom,
  hasValue,
}: {
  center: [number, number];
  zoom: number;
  hasValue: boolean;
}) {
  const map = useMap();
  const key = `${center[0]},${center[1]}`;
  const prev = useRef<string>("");
  useEffect(() => {
    if (hasValue) return;
    if (prev.current === key) return;
    prev.current = key;
    map.setView(center, zoom);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, hasValue]);
  return null;
}

export default function CoordinatePicker({
  value,
  center,
  zoom = 12,
  onPick,
}: {
  value: { lat: number; lng: number } | null;
  center: [number, number];
  zoom?: number;
  onPick: (lat: number, lng: number) => void;
}) {
  return (
    <MapContainer
      center={value ? [value.lat, value.lng] : center}
      zoom={value ? 15 : zoom}
      style={{ height: 220, width: "100%", borderRadius: 8 }}
      scrollWheelZoom
    >
      <ThemedTileLayer />
      <ClickCapture onPick={onPick} />
      <RecenterOnChange center={center} zoom={zoom} hasValue={!!value} />
      {value && <Marker position={[value.lat, value.lng]} icon={pinIcon} />}
    </MapContainer>
  );
}
