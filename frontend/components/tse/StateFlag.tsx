"use client";

/**
 * Bandeira de estado brasileiro (UF).
 *
 * Servidas LOCALMENTE de /public/flags/{UF}.png — antes vinha do Wikimedia
 * (Special:FilePath), que é lento e sofre rate-limit 429 (as bandeiras sumiam).
 * Agora é instantâneo e confiável. onError -> fallback com a sigla.
 */
import { useState } from "react";

// UFs com bandeira local disponível (frontend/public/flags/{UF}.png)
const VALID_UFS = new Set([
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
  "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
  "SP", "SE", "TO",
]);

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
  const dim = SIZE[size];

  if (!VALID_UFS.has(u) || failed) {
    return (
      <span
        className={`inline-grid place-items-center ${dim} rounded-sm bg-muted text-[9px] font-bold text-muted-foreground border border-border ${className}`}
        title={u}
      >
        {u}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/flags/${u}.png`}
      alt={`Bandeira ${u}`}
      title={u}
      onError={() => setFailed(true)}
      className={`inline-block ${dim} object-cover rounded-sm border border-border/60 ${className}`}
    />
  );
}
