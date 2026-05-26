"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { saveAuth, type AuthData } from "@/lib/auth";

// Suspense wrapper exigido pelo Next 14 quando o filho usa useSearchParams.
// Sem isso, `next build` falha em prerender.
export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-screen grid place-items-center" />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const nextUrl = search.get("next") ?? "/dashboard";

  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await api<AuthData>("/v1/auth/login", {
        method: "POST",
        body: { tenant_slug: tenantSlug, email, password },
      });
      saveAuth(data);
      router.push(nextUrl);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro inesperado, tente novamente.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center px-4 relative overflow-hidden">
      {/* Fundo com gradiente + glow */}
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-primary/5" />
      <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-primary/10 blur-3xl" />
      <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl" />

      <div className="relative w-full max-w-sm">
        {/* Marca — logo horizontal oficial (M + MARENOSTRUM + tagline) */}
        <div className="flex flex-col items-center mb-8">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo-wordmark.png"
            alt="MareNostrum — Inteligência de dados & consultoria"
            className="w-64 max-w-full h-auto object-contain"
          />
        </div>

        <form
          onSubmit={onSubmit}
          className="bg-card/80 backdrop-blur rounded-2xl shadow-xl border border-border p-8 space-y-5"
        >
          <Field
            label="Campanha (slug)"
            value={tenantSlug}
            onChange={setTenantSlug}
            autoComplete="organization"
            placeholder="ex: candidato-joao-2026"
            required
          />
          <Field
            label="Email"
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="username"
            required
          />
          <Field
            label="Senha"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            required
          />

          {error && (
            <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-md p-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-gradient-to-r from-primary to-blue-600 hover:opacity-90 disabled:opacity-60 text-white font-semibold py-2.5 transition shadow-lg shadow-primary/20"
          >
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <p className="text-center text-xs text-muted-foreground mt-5">
          Dados eleitorais públicos · Fonte: TSE
        </p>
      </div>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  ...rest
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type">) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition"
        {...rest}
      />
    </label>
  );
}
