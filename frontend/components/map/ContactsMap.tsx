"use client";

/**
 * Mapa Leaflet com marcadores dos contatos.
 *
 * Por que este componente e separado e importado via next/dynamic({ssr:false}):
 *   Leaflet acessa `window`/`document` no escopo do modulo. Se Next tentar
 *   renderizar no servidor, da `ReferenceError: window is not defined`.
 *   O wrapper da pagina importa este componente com `ssr: false` — assim
 *   o codigo do mapa so executa no browser.
 *
 * Por que o marker e customizado (DivIcon):
 *   Os PNGs padrao do Leaflet usam caminhos relativos que quebram com
 *   bundlers (Next/Webpack). DivIcon resolve usando SVG inline.
 */
import { useEffect, useState } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import { toast } from "sonner";

import "leaflet/dist/leaflet.css";

import { api, ApiError } from "@/lib/api";
import { CONTACT_TYPE_LABELS, type Contact } from "@/lib/types";

// Juiz de Fora - MG: ponto neutro como centro inicial.
// Em prod, podemos pegar a cidade do tenant ou do primeiro contato.
const DEFAULT_CENTER: [number, number] = [-21.7642, -43.3496];
const DEFAULT_ZOOM = 12;

// Pin SVG inline — evita o bug dos PNG do Leaflet em bundlers.
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

export default function ContactsMap() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Contact[]>("/v1/contacts/map")
      .then(setContacts)
      .catch((err) => {
        const msg = err instanceof ApiError ? err.message : "Erro ao carregar mapa.";
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="relative h-[calc(100vh-3.5rem)] w-full">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        scrollWheelZoom
        className="h-full w-full"
      >
        <TileLayer
          // OpenStreetMap — gratuito, sem chave de API. Atribuicao obrigatoria.
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {contacts.map((c) =>
          c.latitude != null && c.longitude != null ? (
            <Marker
              key={c.id}
              position={[c.latitude, c.longitude]}
              icon={pinIcon}
            >
              <Popup>
                <div className="text-sm">
                  <p className="font-semibold">{c.full_name}</p>
                  <p className="text-muted-foreground">
                    {CONTACT_TYPE_LABELS[c.type]}
                  </p>
                  {c.neighborhood && (
                    <p className="text-xs mt-1">{c.neighborhood}</p>
                  )}
                  {c.phone && <p className="text-xs">{c.phone}</p>}
                </div>
              </Popup>
            </Marker>
          ) : null,
        )}
      </MapContainer>

      {/* Overlay com contador no canto */}
      <div className="absolute top-4 right-4 z-[1000] bg-card border rounded-lg shadow px-3 py-2 text-sm">
        {loading ? (
          <span className="text-muted-foreground">Carregando...</span>
        ) : (
          <span>
            <strong>{contacts.length}</strong>{" "}
            <span className="text-muted-foreground">
              {contacts.length === 1 ? "contato no mapa" : "contatos no mapa"}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}
