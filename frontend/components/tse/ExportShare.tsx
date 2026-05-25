"use client";

/**
 * Botoes de Exportar (PNG) e Compartilhar (copiar link) pra uma analise.
 * - Exportar: captura o elemento referenciado como imagem PNG (html-to-image).
 * - Compartilhar: copia a URL atual (que ja codifica os filtros) pro clipboard.
 */
import { Download, Link2, Loader2 } from "lucide-react";
import { useState, type RefObject } from "react";
import { toPng } from "html-to-image";
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
      const dataUrl = await toPng(targetRef.current, {
        backgroundColor: "#1c1b1a",
        pixelRatio: 2,
        cacheBust: true,
      });
      const a = document.createElement("a");
      a.download = `${filename}.png`;
      a.href = dataUrl;
      a.click();
      toast.success("Imagem exportada!");
    } catch {
      toast.error("Falha ao exportar imagem.");
    } finally {
      setBusy(false);
    }
  }

  async function share() {
    const url = shareUrl ?? window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ url, title: "Análise MareNostrum" });
      } else {
        await navigator.clipboard.writeText(url);
        toast.success("Link copiado!");
      }
    } catch {
      /* usuario cancelou */
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={exportPng}
        disabled={busy}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border bg-card hover:border-primary/60 text-sm transition-colors disabled:opacity-50"
        title="Exportar como imagem"
      >
        {busy ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Download className="w-4 h-4" />
        )}
        Exportar
      </button>
      <button
        onClick={share}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border bg-card hover:border-primary/60 text-sm transition-colors"
        title="Compartilhar link"
      >
        <Link2 className="w-4 h-4" />
        Compartilhar
      </button>
    </div>
  );
}
