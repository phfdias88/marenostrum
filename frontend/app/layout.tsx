import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";

const _SITE_NAME = "MareNostrum";
const _TITLE = "MareNostrum — Inteligência política e eleitoral";
const _DESC =
  "Gestão de campanhas, CRM eleitoral e inteligência de dados eleitorais.";

export const metadata: Metadata = {
  title: { default: _TITLE, template: "%s · MareNostrum" },
  description: _DESC,
  applicationName: _SITE_NAME,
  openGraph: {
    type: "website",
    siteName: _SITE_NAME,
    title: _TITLE,
    description: _DESC,
    locale: "pt_BR",
    images: [
      {
        url: "/logo-wordmark.png",
        width: 1200,
        height: 208,
        alt: "MareNostrum — Inteligência de Dados & Consultoria",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: _TITLE,
    description: _DESC,
    images: ["/logo-wordmark.png"],
  },
};

// Anti-FOUC: aplica a classe do tema ANTES da página pintar.
// Lê localStorage("mn_theme"); fallback "dark".
// Tambem patcha HTMLCanvasElement.getContext pra silenciar o warning do
// Leaflet "Canvas2D: Multiple readback operations" (leaflet usa preferCanvas
// + getImageData mas nao seta willReadFrequently no getContext).
const THEME_INIT_SCRIPT = `
(function(){try{
  var t=localStorage.getItem("mn_theme");
  var c=document.documentElement.classList;
  if(t==="light"){c.add("light");c.remove("dark");}
  else{c.add("dark");c.remove("light");}
}catch(e){}
try{
  var p=HTMLCanvasElement.prototype, orig=p.getContext;
  p.getContext=function(type, attrs){
    if(type==="2d"){
      attrs=attrs||{};
      if(attrs.willReadFrequently===undefined) attrs.willReadFrequently=true;
    }
    return orig.call(this, type, attrs);
  };
}catch(e){}})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="dark">
      <head>
        {/* Pre-connect ao backend e ao tile do mapa — economiza ~100-300ms
            no primeiro request, especialmente em mobile/3G/4G. */}
        <link rel="preconnect" href="https://srv1412083.hstgr.cloud" />
        <link rel="dns-prefetch" href="https://a.basemaps.cartocdn.com" />
        <link rel="dns-prefetch" href="https://cdn.tse.jus.br" />
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        {children}
        {/* CSS em globals.css empurra o container do toast pra cima da
            BottomNav no mobile (sonner nao tem mobileOffset nessa versao). */}
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
