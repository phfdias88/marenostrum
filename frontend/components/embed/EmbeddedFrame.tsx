"use client";

/**
 * EmbeddedFrame — wrapper reutilizavel pra integrar sistemas externos via iframe.
 *
 * Responsabilidades:
 * 1. Renderiza iframe ocupando toda a area util (h-[calc(100vh-3.5rem)])
 * 2. Skeleton elegante enquanto a pagina externa nao dispara `onLoad`
 * 3. Mensagem amigavel se a URL nao foi configurada (env vazio ou example.com)
 * 4. Hint informativa se demora demais (provavel CSP frame-ancestors bloqueando)
 *
 * NOTA SOBRE SEGURANCA:
 * O atributo `sandbox` esta DELIBERADAMENTE OMITIDO — sistemas administrativos
 * (Looker, Metabase, Sonar) precisam de cookies, storage e popups pra funcionar.
 * Restringir via sandbox quebraria login do sistema embutido. A confianca aqui
 * e' do operador que configurou a URL — embed so' do que o cliente controla.
 *
 * Se um dia precisar reduzir superficie de ataque, adicionar:
 *   sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
 */
import { AlertCircle, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

type Props = {
  src: string | undefined;
  title: string;
  /** Nome amigavel da env var, para mensagem de "nao configurado" */
  envVarName: string;
};

// URLs reconhecidas como placeholder — nao tentamos carregar.
function isPlaceholder(url: string): boolean {
  return /^https?:\/\/(example|placeholder)\.(com|org|net)/i.test(url);
}

export function EmbeddedFrame({ src, title, envVarName }: Props) {
  const notConfigured = !src || isPlaceholder(src);

  if (notConfigured) {
    return <NotConfigured envVarName={envVarName} />;
  }

  return <LiveFrame src={src!} title={title} />;
}

// -------------------------------------------------------------------- live


function LiveFrame({ src, title }: { src: string; title: string }) {
  const [loaded, setLoaded] = useState(false);
  const [slow, setSlow] = useState(false);

  // Se o iframe nao disparar onLoad em 8s, mostra dica (CSP / X-Frame-Options).
  useEffect(() => {
    if (loaded) return;
    const t = setTimeout(() => setSlow(true), 8000);
    return () => clearTimeout(t);
  }, [loaded]);

  return (
    <div className="relative h-[calc(100vh-3.5rem)] w-full">
      {!loaded && (
        <div className="absolute inset-0 z-10 bg-background">
          <LoadingDashboardSkeleton hint={slow} />
        </div>
      )}
      <iframe
        src={src}
        title={title}
        onLoad={() => setLoaded(true)}
        loading="lazy"
        referrerPolicy="strict-origin-when-cross-origin"
        // Permite uso de camera/microfone caso o sistema embutido precise
        // (ex.: sonar com video). Pode reduzir se nao for usado.
        allow="clipboard-read; clipboard-write; fullscreen"
        className={cn(
          "h-full w-full border-0 transition-opacity duration-300",
          loaded ? "opacity-100" : "opacity-0",
        )}
      />
    </div>
  );
}


// ---------------------------------------------------------------- loading


function LoadingDashboardSkeleton({ hint }: { hint: boolean }) {
  return (
    <div className="h-full w-full p-8 space-y-6 max-w-7xl mx-auto">
      {/* Header simulado */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-9 w-32" />
      </div>

      {/* Cards de KPI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl border bg-card p-4 space-y-3">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-24" />
          </div>
        ))}
      </div>

      {/* Grafico grande */}
      <div className="rounded-xl border bg-card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-8 w-24" />
        </div>
        <Skeleton className="h-64 w-full" />
      </div>

      {/* Hint se demorar */}
      {hint && (
        <div className="flex items-start gap-2 text-sm text-muted-foreground border rounded-md p-3 bg-muted/30">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <p>
            A carga está demorando mais que o esperado. Se ficar em branco,
            verifique se o servidor externo permite embedding (cabeçalhos
            <code className="mx-1 text-xs bg-muted px-1.5 py-0.5 rounded">
              X-Frame-Options
            </code>
            ou
            <code className="mx-1 text-xs bg-muted px-1.5 py-0.5 rounded">
              Content-Security-Policy: frame-ancestors
            </code>
            ).
          </p>
        </div>
      )}
    </div>
  );
}


// --------------------------------------------------------- not configured


function NotConfigured({ envVarName }: { envVarName: string }) {
  return (
    <div className="h-[calc(100vh-3.5rem)] w-full grid place-items-center bg-muted/20 px-6">
      <div className="max-w-md text-center space-y-3">
        <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-muted">
          <Settings2 className="h-6 w-6 text-muted-foreground" />
        </div>
        <h2 className="text-lg font-semibold">Integração em breve</h2>
        <p className="text-sm text-muted-foreground">
          Este recurso ainda não está habilitado para a sua campanha.
          Entre em contato com o suporte MareNostrum se precisar usá-lo.
        </p>
        {/* Hint tecnico minimo so pra ops — escondido em comentario HTML
            mas ainda inspecionavel via devtools, evita "magic" pro suporte */}
        <p className="text-[10px] text-muted-foreground/40 mt-4" data-ops-hint>
          <span className="hidden">env: {envVarName}</span>
        </p>
      </div>
    </div>
  );
}
