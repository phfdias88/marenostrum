"use client";

/**
 * /dashboard/map — mapa em tela cheia com pins dos contatos georreferenciados.
 *
 * O ContactsMap e importado dinamicamente com ssr:false porque Leaflet
 * acessa `window` no escopo do modulo (quebraria no build do servidor).
 */
import dynamic from "next/dynamic";

const ContactsMap = dynamic(() => import("@/components/map/ContactsMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-[calc(100dvh-3.5rem-64px-env(safe-area-inset-bottom))] md:h-[calc(100dvh-3.5rem)] grid place-items-center text-muted-foreground">
      Carregando mapa...
    </div>
  ),
});

export default function MapPage() {
  return <ContactsMap />;
}
