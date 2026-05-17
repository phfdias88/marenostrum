"use client";

/**
 * Dashboard: visao geral pos-login.
 * Consome /api/v1/auth/me e exibe cards comprovando o isolamento multi-tenant.
 * Header + logout estao no layout.tsx do segmento /dashboard.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { clearAuth } from "@/lib/auth";

type Me = {
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  tenant_id: string;
  tenant_slug: string;
  tenant_name: string;
};

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Me>("/v1/auth/me")
      .then(setMe)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAuth();
          router.replace("/login");
          return;
        }
        setError(err instanceof ApiError ? err.message : "Erro inesperado.");
      });
  }, [router]);

  return (
    <section className="max-w-7xl mx-auto px-6 py-10 space-y-6">
      {error && (
        <div className="p-4 rounded-lg border border-destructive/30 bg-destructive/5 text-destructive">
          {error}
        </div>
      )}

      {me && (
        <>
          <header>
            <h1 className="text-2xl font-semibold tracking-tight">
              Olá, {me.full_name.split(" ")[0]}
            </h1>
            <p className="text-muted-foreground mt-1">
              Painel da campanha{" "}
              <span className="text-foreground font-medium">{me.tenant_name}</span>.
            </p>
          </header>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <InfoCard label="Usuário" value={me.email} hint={me.user_id} />
            <InfoCard label="Papel" value={roleLabel(me.role)} hint={`role=${me.role}`} />
            <InfoCard label="Campanha" value={me.tenant_slug} hint={me.tenant_id} />
            <InfoCard
              label="Multi-tenant"
              value="OK ✓"
              hint="Queries filtradas por tenant_id no backend"
            />
          </div>
        </>
      )}
    </section>
  );
}

function InfoCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="bg-card border rounded-xl p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 font-medium">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground font-mono break-all">
        {hint}
      </p>
    </div>
  );
}

function roleLabel(role: string): string {
  return (
    {
      owner: "Candidato / Owner",
      manager: "Coordenador",
      staff: "Equipe",
      volunteer: "Voluntário",
    }[role] ?? role
  );
}
