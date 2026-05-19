import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "MareNostrum — Inteligência política e eleitoral",
    template: "%s · MareNostrum",
  },
  description:
    "Gestão de campanhas, CRM eleitoral e análise de dados públicos do TSE.",
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
