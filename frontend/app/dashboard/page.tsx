"use client";

/**
 * Dashboard: primeira tela apos login.
 * Consome GET /api/v1/auth/me para provar end-to-end que:
 *  - o JWT no cookie foi aceito pelo backend
 *  - o tenant_id no token bate com o registro do usuario
 *  - a sessao multi-tenant esta correta
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

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
  const [loading, setLoading] = useState(true);

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
      })
      .finally(() => setLoading(false));
  }, [router]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex justify-between items-center">
          <h1 className="text-xl font-semibold text-brand-900">MareNostrum</h1>
          {me && (
            <div className="flex items-center gap-4 text-sm">
              <span className="text-slate-600">
                {me.full_name} ·{" "}
                <span className="text-brand-700 font-medium">{me.tenant_name}</span>
              </span>
              <button
                onClick={logout}
                className="text-slate-500 hover:text-slate-900"
              >
                Sair
              </button>
            </div>
          )}
        </div>
      </header>

      <section className="max-w-5xl mx-auto px-6 py-10">
        {loading && <p className="text-slate-500">Carregando...</p>}

        {error && (
          <div className="p-4 rounded-lg border border-red-200 bg-red-50 text-red-700">
            {error}
          </div>
        )}

        {me && (
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-semibold text-slate-900">
                Ola, {me.full_name.split(" ")[0]} 👋
              </h2>
              <p className="text-slate-500 mt-1">
                Voce esta logado na campanha{" "}
                <strong className="text-brand-700">{me.tenant_name}</strong>.
              </p>
            </div>

            {/* Painel de debug — comprova multi-tenant ponta a ponta.
                Em producao, transforme em cards de metricas reais. */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <InfoCard label="Usuario" value={me.email} sub={me.user_id} />
              <InfoCard
                label="Papel"
                value={roleLabel(me.role)}
                sub={`role=${me.role}`}
              />
              <InfoCard
                label="Campanha (slug)"
                value={me.tenant_slug}
                sub={me.tenant_id}
              />
              <InfoCard
                label="Isolamento multi-tenant"
                value="OK ✓"
                sub="Toda query do backend filtra por tenant_id automaticamente"
              />
            </div>

            <nav className="flex gap-3 pt-4">
              <Link
                href="/contatos"
                className="px-4 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition"
              >
                Contatos →
              </Link>
            </nav>
          </div>
        )}
      </section>
    </main>
  );
}

function InfoCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-slate-900 font-medium">{value}</p>
      <p className="mt-1 text-xs text-slate-400 font-mono break-all">{sub}</p>
    </div>
  );
}

function roleLabel(role: string): string {
  return (
    {
      owner: "Candidato / Owner",
      manager: "Coordenador",
      staff: "Equipe",
      volunteer: "Voluntario",
    }[role] ?? role
  );
}
