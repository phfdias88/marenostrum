"use client";

/**
 * Bandeira de estado brasileiro (UF).
 *
 * Usa Wikimedia Commons via Special:FilePath (URL estavel, redireciona pro
 * arquivo real sem depender do hash do diretorio). onError -> fallback texto.
 */
import { useState } from "react";

// UF -> nome do arquivo da bandeira no Wikimedia Commons
const FLAG_FILE: Record<string, string> = {
  AC: "Bandeira do Acre.svg",
  AL: "Bandeira de Alagoas.svg",
  AP: "Bandeira do Amapá.svg",
  AM: "Bandeira do Amazonas.svg",
  BA: "Bandeira da Bahia.svg",
  CE: "Bandeira do Ceará.svg",
  DF: "Bandeira do Distrito Federal (Brasil).svg",
  ES: "Bandeira do Espírito Santo.svg",
  GO: "Flag of Goiás.svg",
  MA: "Bandeira do Maranhão.svg",
  MT: "Bandeira de Mato Grosso.svg",
  MS: "Bandeira de Mato Grosso do Sul.svg",
  MG: "Bandeira de Minas Gerais.svg",
  PA: "Bandeira do Pará.svg",
  PB: "Bandeira da Paraíba.svg",
  PR: "Bandeira do Paraná.svg",
  PE: "Bandeira de Pernambuco.svg",
  PI: "Bandeira do Piauí.svg",
  RJ: "Bandeira do estado do Rio de Janeiro.svg",
  RN: "Bandeira do Rio Grande do Norte.svg",
  RS: "Bandeira do Rio Grande do Sul.svg",
  RO: "Bandeira de Rondônia.svg",
  RR: "Bandeira de Roraima.svg",
  SC: "Bandeira de Santa Catarina.svg",
  SP: "Bandeira do estado de São Paulo.svg",
  SE: "Bandeira de Sergipe.svg",
  TO: "Bandeira do Tocantins.svg",
};

const SIZE: Record<string, string> = {
  sm: "w-5 h-3.5",
  md: "w-7 h-5",
  lg: "w-10 h-7",
};

export function StateFlag({
  uf,
  size = "sm",
  className = "",
}: {
  uf: string | null | undefined;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const u = (uf ?? "").toUpperCase();
  const file = FLAG_FILE[u];
  const dim = SIZE[size];

  if (!file || failed) {
    return (
      <span
        className={`inline-grid place-items-center ${dim} rounded-sm bg-muted text-[9px] font-bold text-muted-foreground border border-border ${className}`}
        title={u}
      >
        {u}
      </span>
    );
  }

  const src = `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(
    file,
  )}?width=80`;

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={`Bandeira ${u}`}
      title={u}
      loading="lazy"
      onError={() => setFailed(true)}
      className={`inline-block ${dim} object-cover rounded-sm border border-border/60 ${className}`}
    />
  );
}
