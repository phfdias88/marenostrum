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
    <main className="min-h-screen grid place-items-center px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-slate-200 p-8 space-y-5"
      >
        <div>
          <h1 className="text-2xl font-semibold text-brand-900">MareNostrum</h1>
          <p className="text-sm text-slate-500">Entre na sua campanha</p>
        </div>

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
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md p-2">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-60 text-white font-medium py-2.5 transition"
        >
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
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
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 outline-none"
        {...rest}
      />
    </label>
  );
}
