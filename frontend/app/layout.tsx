import type { Metadata, Viewport } from "next";
import { MnToaster } from "@/components/ui/MnToaster";
import "./globals.css";

const _SITE_NAME = "MareNostrum";
const _TITLE = "MareNostrum · Inteligência política e eleitoral";
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
        alt: "MareNostrum · Inteligência de Dados & Consultoria",
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

// viewportFit cover libera as safe-areas do iOS (notch) pro layout usar.
// theme-color NÃO fica aqui: fixo em dark pintava a moldura do navegador de
// marrom-escuro também no tema claro — o THEME_INIT_SCRIPT (antes do paint) e
// o ThemeToggle (no toggle) setam a meta com a cor do tema ativo.
export const viewport: Viewport = {
  viewportFit: "cover",
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
  var m=document.createElement("meta");m.name="theme-color";
  m.content=(t==="light")?"#FAF8F5":"#161311";
  document.head.appendChild(m);
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
        <link rel="preconnect" href="https://a.basemaps.cartocdn.com" crossOrigin="anonymous" />
        <link rel="dns-prefetch" href="https://b.basemaps.cartocdn.com" />
        <link rel="dns-prefetch" href="https://cdn.tse.jus.br" />
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        {children}
        {/* MnToaster segue o tema da casa (mn_theme/classe no <html>).
            CSS em globals.css empurra o container do toast pra cima da
            BottomNav no mobile (sonner nao tem mobileOffset nessa versao). */}
        <MnToaster />
      </body>
    </html>
  );
}
