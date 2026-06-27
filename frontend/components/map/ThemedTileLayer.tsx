"use client";

/**
 * TileLayer com camada escolhida pelo usuário (claro / escuro / satélite),
 * via useMapLayout (localStorage, compartilhado entre os mapas).
 *
 * Claro    -> CartoDB Voyager (creme, alta legibilidade) — padrão
 * Escuro   -> CartoDB Dark (carvão com labels)
 * Satélite -> Esri World Imagery
 *
 * `key={layout}` força o Leaflet a recriar o TileLayer ao trocar de camada.
 */
import { TileLayer } from "react-leaflet";

import { useMapLayout } from "@/lib/useMapLayout";

const ATTRIB_CARTO =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';
const ATTRIB_ESRI =
  'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community';

const URL_LIGHT =
  "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";
const URL_DARK =
  "https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png";
const URL_SAT =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

export function ThemedTileLayer() {
  const [layout] = useMapLayout();

  if (layout === "satellite") {
    return (
      <TileLayer
        key="satellite"
        attribution={ATTRIB_ESRI}
        url={URL_SAT}
        maxZoom={19}
      />
    );
  }

  return (
    <TileLayer
      key={layout}
      attribution={ATTRIB_CARTO}
      url={layout === "dark" ? URL_DARK : URL_LIGHT}
      subdomains={["a", "b", "c", "d"]}
      maxZoom={19}
    />
  );
}
