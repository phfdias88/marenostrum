"use client";

/**
 * /dashboard/analytics — embute o sistema externo de analise de votacoes.
 * Toda a logica de iframe + skeleton + fallback mora em EmbeddedFrame.
 */
import { EmbeddedFrame } from "@/components/embed/EmbeddedFrame";

export default function AnalyticsPage() {
  return (
    <EmbeddedFrame
      src={process.env.NEXT_PUBLIC_ANALYTICS_URL}
      title="Análises de Votação"
      envVarName="NEXT_PUBLIC_ANALYTICS_URL"
    />
  );
}
