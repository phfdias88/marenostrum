"use client";

/**
 * Mapa Leaflet — 2 modos:
 *   "contacts" → pins SVG dos contatos georeferenciados (Contact.lat/lng)
 *   "heatmap"  → mapa de calor de votos por local (VotingPlace.votes)
 *
 * Por que este componente é importado via next/dynamic({ssr:false}):
 *   Leaflet acessa `window`/`document` no escopo do modulo. Sem ssr:false
 *   o build do Next dá `ReferenceError: window is not defined`.
 */
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet.heat"; // side-effect — registra L.heatLayer
import { MapContainer, Marker, Popup, useMap } from "react-leaflet";
import { Flame, MapPinned } from "lucide-react";
import { toast } from "sonner";

import "leaflet/dist/leaflet.css";

import { api, ApiError } from "@/lib/api";
import {
  CONTACT_TYPE_LABELS,
  type Contact,
  type HeatmapResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { ThemedTileLayer } from "./ThemedTileLayer";

// Tipos não-tipados do leaflet.heat
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

// Juiz de Fora - MG: centro padrão (sobrescrito pelo primeiro ponto carregado)
const DEFAULT_CENTER: [number, number] = [-21.7642, -43.3496];
const DEFAULT_ZOOM = 12;

// Pin SVG inline (evita bug dos PNGs Leaflet em bundlers)
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
  popupAnchor: [0, -32],
});

type Mode = "contacts" | "heatmap";

export default function ContactsMap() {
  const [mode, setMode] = useState<Mode>("contacts");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const fetcher =
      mode === "contacts"
        ? api<Contact[]>("/v1/contacts/map").then((data) => setContacts(data))
        : api<HeatmapResponse>("/v1/voting-places/heatmap").then((data) =>
            setHeatmap(data),
          );
    fetcher
      .catch((err) => {
        toast.error(err instanceof ApiError ? err.message : "Erro ao carregar mapa.");
      })
      .finally(() => setLoading(false));
  }, [mode]);

  return (
    <div className="relative w-full h-[calc(100dvh-3.5rem-64px-env(safe-area-inset-bottom))] md:h-[calc(100dvh-3.5rem)]">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        scrollWheelZoom
        className="h-full w-full"
      >
        <ThemedTileLayer />

        {mode === "contacts" &&
          contacts.map((c) =>
            c.latitude != null && c.longitude != null ? (
              <Marker key={c.id} position={[c.latitude, c.longitude]} icon={pinIcon}>
                <Popup>
                  <div className="text-sm">
                    <p className="font-semibold">{c.full_name}</p>
                    <p className="text-muted-foreground">
                      {CONTACT_TYPE_LABELS[c.type]}
                    </p>
                    {c.neighborhood && <p className="text-xs mt-1">{c.neighborhood}</p>}
                    {c.phone && <p className="text-xs">{c.phone}</p>}
                  </div>
                </Popup>
              </Marker>
            ) : null,
          )}

        {mode === "heatmap" && heatmap && <HeatLayer data={heatmap} />}
      </MapContainer>

      {/* Toggle de modo (canto superior esquerdo) */}
      <ModeToggle mode={mode} onChange={setMode} />

      {/* Stats no canto direito */}
      <Stats mode={mode} loading={loading} contacts={contacts} heatmap={heatmap} />
    </div>
  );
}


// ----------------------------------------------------------- HeatLayer

function HeatLayer({ data }: { data: HeatmapResponse }) {
  const map = useMap();
  const layerRef = useRef<L.Layer | null>(null);

  useEffect(() => {
    // Remove camada anterior (re-render)
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    if (data.points.length === 0) return;

    // Leaflet.heat espera [lat, lng, intensity]. intensity já vem 0..1 do backend.
    const points: Array<[number, number, number]> = data.points.map((p) => [
      p.lat,
      p.lng,
      p.intensity,
    ]);

    const heat = L.heatLayer(points, {
      radius: 25,
      blur: 18,
      maxZoom: 17,
      max: 1.0, // intensidade já normalizada
      minOpacity: 0.3,
      gradient: {
        0.0: "#1e6fd9", // azul (poucos votos)
        0.3: "#5cb85c", // verde
        0.6: "#f0ad4e", // amarelo
        0.85: "#f97316", // laranja
        1.0: "#dc2626", // vermelho (max)
      },
    });
    heat.addTo(map);
    layerRef.current = heat;

    // Auto-centraliza no primeiro ponto se está fora da view
    const firstPoint = data.points[0];
    if (firstPoint) {
      const bounds = L.latLngBounds(
        data.points.map((p) => [p.lat, p.lng] as [number, number]),
      );
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
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


// ----------------------------------------------------------- ModeToggle

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const Btn = ({
    value, icon: Icon, label,
  }: {
    value: Mode;
    icon: typeof MapPinned;
    label: string;
  }) => (
    <button
      onClick={() => onChange(value)}
      className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors",
        mode === value
          ? "bg-foreground text-background"
          : "text-muted-foreground hover:text-foreground hover:bg-accent",
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );

  return (
    <div className="absolute top-4 left-4 z-[1000] flex gap-1 bg-card border rounded-lg shadow p-1">
      <Btn value="contacts" icon={MapPinned} label="Contatos" />
      <Btn value="heatmap" icon={Flame} label="Heatmap" />
    </div>
  );
}


// ----------------------------------------------------------- Stats

function Stats({
  mode,
  loading,
  contacts,
  heatmap,
}: {
  mode: Mode;
  loading: boolean;
  contacts: Contact[];
  heatmap: HeatmapResponse | null;
}) {
  let body: React.ReactNode;
  if (loading) {
    body = <span className="text-muted-foreground">Carregando...</span>;
  } else if (mode === "contacts") {
    body = (
      <span>
        <strong>{contacts.length}</strong>{" "}
        <span className="text-muted-foreground">
          {contacts.length === 1 ? "contato" : "contatos"} no mapa
        </span>
      </span>
    );
  } else if (heatmap) {
    body = (
      <div className="space-y-0.5">
        <p>
          <strong>{heatmap.total_places.toLocaleString("pt-BR")}</strong>{" "}
          <span className="text-muted-foreground">locais</span>
        </p>
        <p>
          <strong>{heatmap.total_votes.toLocaleString("pt-BR")}</strong>{" "}
          <span className="text-muted-foreground">votos totais</span>
        </p>
        <p className="text-xs text-muted-foreground">
          Pico em 1 local: <strong>{heatmap.max_votes.toLocaleString("pt-BR")}</strong>
        </p>
      </div>
    );
  } else {
    body = <span className="text-muted-foreground">Sem dados.</span>;
  }

  return (
    <div className="absolute top-4 right-4 z-[1000] bg-card border rounded-lg shadow px-3 py-2 text-sm min-w-[180px]">
      {body}
    </div>
  );
}
