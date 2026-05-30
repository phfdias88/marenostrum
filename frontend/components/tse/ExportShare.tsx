"use client";

/**
 * Botoes de Exportar (PNG) e Compartilhar (copiar link).
 *
 * Notas de robustez (o site roda em HTTP, nao HTTPS):
 * - navigator.clipboard / navigator.share só existem em contexto seguro (HTTPS).
 *   Em HTTP caímos no fallback execCommand('copy') via textarea.
 * - html-to-image quebra facil tentando embutir fontes externas → skipFonts:true.
 */
import { Download, Link2, Loader2 } from "lucide-react";
import { useState, type RefObject } from "react";
import { toast } from "sonner";

export function ExportShare({
  targetRef,
  filename = "analise-marenostrum",
  shareUrl,
}: {
  targetRef: RefObject<HTMLElement>;
  filename?: string;
  shareUrl?: string;
}) {
  const [busy, setBusy] = useState(false);

  async function exportPng() {
    if (!targetRef.current) return;
    setBusy(true);
    try {
      const { toPng } = await import("html-to-image");
      const dataUrl = await toPng(targetRef.current, {
        backgroundColor: "#1c1b1a",
        pixelRatio: 2,
        cacheBust: true,
        skipFonts: true, // evita falha ao embutir fontes externas
      });
      const a = document.createElement("a");
      a.download = `${filename}.png`;
      a.href = dataUrl;
      a.click();
      toast.success("Imagem exportada!");
    } catch (err) {
      console.error("[export] toPng falhou:", err);
      toast.error("Falha ao exportar imagem. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }

  function copyFallback(text: string) {
    // Funciona em HTTP (sem navigator.clipboard)
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  async function share() {
    const url = shareUrl ?? window.location.href;
    // 1) Web Share API (mobile / HTTPS)
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ url, title: "Análise MareNostrum" });
        return;
      } catch {
        /* cancelou — segue pro copy */
      }
    }
    // 2) Clipboard API (HTTPS)
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(url);
        toast.success("Link copiado!");
        return;
      } catch {
        /* cai no fallback */
      }
    }
    // 3) Fallback HTTP
    if (copyFallback(url)) {
      toast.success("Link copiado!");
    } else {
      toast.message("Copie o link:", { description: url });
    }
  }

  return (
    <div className="flex items-center gap-1.5 sm:gap-2">
      <button
        onClick={exportPng}
        disabled={busy}
        className="inline-flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md border border-border bg-card hover:border-primary/60 text-sm transition-colors disabled:opacity-50"
        title="Exportar como imagem"
        aria-label="Exportar como imagem"
      >
        {busy ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Download className="w-4 h-4" />
        )}
        <span className="hidden sm:inline">Exportar</span>
      </button>
      <button
        onClick={share}
        className="inline-flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md border border-border bg-card hover:border-primary/60 text-sm transition-colors"
        title="Compartilhar link"
        aria-label="Compartilhar link"
      >
        <Link2 className="w-4 h-4" />
        <span className="hidden sm:inline">Compartilhar</span>
      </button>
    </div>
  );
}
