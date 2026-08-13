"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Loader2 } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { saveAuth, type AuthData } from "@/lib/auth";
import { Button } from "@/components/ui/button";

// Página onde cai o link do e-mail pós-compra: o comprador define a senha do
// acesso recém-provisionado e já entra (o backend devolve um JWT). Pública
// (fora do matcher do middleware). Token de uso único no ?token=.
export default function SetPasswordPage() {
  return (
    <Suspense fallback={<main className="min-h-screen grid place-items-center" />}>
      <SetPasswordForm />
    </Suspense>
  );
}

function SetPasswordForm() {
  const router = useRouter();
  const search = useSearchParams();
  const token = search.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("Link inválido. Abra o link exatamente como veio no e-mail.");
      return;
    }
    if (password !== confirm) {
      setError("As senhas não conferem.");
      return;
    }
    setLoading(true);
    try {
      const data = await api<AuthData>("/v1/auth/set-password", {
        method: "POST",
        body: { token, password },
      });
      // Login automático: salva o token e entra direto no painel.
      saveAuth(data);
      router.push("/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro inesperado, tente novamente.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      className="min-h-[100dvh] grid place-items-center px-4 py-6 relative overflow-hidden"
      style={{
        paddingTop: "max(env(safe-area-inset-top), 1.5rem)",
        paddingBottom: "max(env(safe-area-inset-bottom), 1.5rem)",
      }}
    >
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-primary/5" />
      <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-primary/10 blur-3xl" />
      <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-primary/10 blur-3xl" />

      <div className="relative w-full max-w-sm">
        <div className="flex flex-col items-center mb-6 sm:mb-8 mn-fade-in">
          <div className="dark:bg-card rounded-2xl px-6 py-4 dark:shadow-lg dark:shadow-black/20 dark:border dark:border-primary/30">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/logo-wordmark.webp`}
              alt="MareNostrum"
              className="w-44 sm:w-56 max-w-full h-auto object-contain hidden dark:block"
            />
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/logo-wordmark-light.webp`}
              alt="MareNostrum"
              className="w-44 sm:w-56 max-w-full h-auto object-contain dark:hidden"
            />
          </div>
        </div>

        <form
          onSubmit={onSubmit}
          className="mn-glass rounded-2xl p-5 sm:p-8 space-y-4 sm:space-y-5 mn-fade-in"
          style={{ animationDelay: "0.1s" }}
        >
          <div className="text-center">
            <h1 className="text-lg font-bold">Bem-vindo!</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Defina sua senha para acessar o sistema.
            </p>
          </div>

          <Field
            label="Nova senha"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            required
          />
          <Field
            label="Confirmar senha"
            type="password"
            value={confirm}
            onChange={setConfirm}
            autoComplete="new-password"
            required
          />
          <p className="text-[11px] text-muted-foreground">
            Mínimo de 10 caracteres.
          </p>

          {error && (
            <p className="text-sm border border-destructive/30 bg-destructive/10 text-destructive rounded-md p-2.5">
              {error}
            </p>
          )}

          <Button
            type="submit"
            disabled={loading}
            className="w-full min-h-[48px] rounded-lg text-base font-semibold"
          >
            {loading ? (
              <>
                <Loader2 className="animate-spin" aria-hidden="true" />
                Salvando...
              </>
            ) : (
              "Definir senha e entrar"
            )}
          </Button>
        </form>
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
  const [show, setShow] = useState(false);
  const isPassword = type === "password";
  const effectiveType = isPassword && show ? "text" : type;

  return (
    <label className="block">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <div className="relative mt-1.5">
        <input
          type={effectiveType}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={
            "w-full rounded-lg border border-border bg-background px-3.5 py-3 text-base focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition" +
            (isPassword ? " pr-12" : "")
          }
          {...rest}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            aria-label={show ? "Ocultar senha" : "Mostrar senha"}
            className="absolute right-1 top-1/2 -translate-y-1/2 inline-flex h-11 w-11 items-center justify-center rounded-md text-muted-foreground hover:text-foreground transition-colors"
          >
            {show ? (
              <EyeOff className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Eye className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        )}
      </div>
    </label>
  );
}
