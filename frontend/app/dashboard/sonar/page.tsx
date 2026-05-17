"use client";

/**
 * /dashboard/sonar — embute o sistema Sonar de atendimentos.
 */
import { EmbeddedFrame } from "@/components/embed/EmbeddedFrame";

export default function SonarPage() {
  return (
    <EmbeddedFrame
      src={process.env.NEXT_PUBLIC_SONAR_URL}
      title="Atendimentos Sonar"
      envVarName="NEXT_PUBLIC_SONAR_URL"
    />
  );
}
