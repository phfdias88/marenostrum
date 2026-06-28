"use client";

/**
 * /dashboard/sonar — embute o sistema Sonar de atendimentos.
 */
import { EmbeddedFrame } from "@/components/embed/EmbeddedFrame";

export default function SonarPage() {
  const src = process.env.NEXT_PUBLIC_SONAR_URL;
  const notConfigured =
    !src || /^https?:\/\/(example|placeholder)\.(com|org|net)/i.test(src);

  if (notConfigured) {
    return (
      <div className="h-[calc(100vh-3.5rem)] w-full grid place-items-center bg-muted/20 px-6">
        <p className="max-w-md text-center text-sm text-muted-foreground">
          Integração de atendimentos ainda não configurada. Fale com o suporte.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)] w-full">
      <p className="px-4 py-2 text-xs text-muted-foreground border-b border-border">
        Sistema de atendimentos Sonar, integrado à sua campanha.
      </p>
      <div className="flex-1 min-h-0">
        <EmbeddedFrame
          src={src}
          title="Atendimentos Sonar"
          envVarName="NEXT_PUBLIC_SONAR_URL"
        />
      </div>
    </div>
  );
}
