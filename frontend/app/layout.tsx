import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";

const _SITE_NAME = "MareNostrum";
const _TITLE = "MareNostrum — Inteligência política e eleitoral";
const _DESC =
  "Gestão de campanhas, CRM eleitoral e análise de dados públicos do TSE.";

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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        {children}
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
