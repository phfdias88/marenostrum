"use client";

/**
 * TileLayer que troca tile escuro/claro conforme o tema do app.
 *
 * Dark  -> CartoDB Dark Matter (carvao com label dourado/champanhe)
 * Light -> CartoDB Voyager (creme suave, alta legibilidade)
 *
 * Re-renderiza quando o tema muda (via key) — Leaflet recria o TileLayer.
 */
import { TileLayer } from "react-leaflet";

const ATTRIB =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';

// Voyager (creme/claro, alta legibilidade) — usado nos dois temas porque o
// Dark Matter ficou ilegível: pontos pequenos sumindo no fundo escuro. O claro
// destaca melhor os marcadores coloridos e o pulse dourado dos top munis.
const URL_VOYAGER =
  "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

export function ThemedTileLayer() {
  return (
    <TileLayer
      attribution={ATTRIB}
      url={URL_VOYAGER}
      subdomains={["a", "b", "c", "d"]}
      maxZoom={19}
    />
  );
}
