"use client";

/**
 * Dialog de importacao CSV.
 *
 * Fluxo:
 * 1. Usuario clica "Baixar planilha modelo" -> /contatos-modelo.csv (estatico)
 * 2. Preenche, seleciona arquivo, clica Importar
 * 3. Spinner + Toast "carregando", POST /v1/contacts/import (multipart)
 * 4. Resumo no proprio dialog: imported / skipped / erros (truncados)
 * 5. Tabela atualiza via onImported() (chamado mesmo se imported=0,
 *    pra refletir possiveis criacoes parciais)
 */
import { Download, FileSpreadsheet, Loader2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { ImportResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

type Props = {
  onImported: () => void;
  children: React.ReactNode; // trigger
};

export function ImportContactsDialog({ onImported, children }: Props) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setFile(null);
    setResult(null);
    setBusy(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleImport() {
    if (!file) return;

    setBusy(true);
    setResult(null);
    const loadingToast = toast.loading(`Importando ${file.name}...`);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api<ImportResult>("/v1/contacts/import", {
        method: "POST",
        body: form,
      });
      setResult(res);

      // Mensagem do toast varia conforme resultado
      const msg =
        res.imported > 0
          ? `${res.imported} contato(s) importado(s)${
              res.skipped > 0 ? `, ${res.skipped} pulado(s)` : ""
            }.`
          : `Nenhum contato importado (${res.skipped} pulado(s)).`;

      if (res.imported > 0) toast.success(msg, { id: loadingToast });
      else toast.warning(msg, { id: loadingToast });

      // Atualiza a tabela mesmo que parcialmente
      if (res.imported > 0) onImported();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Falha ao importar.";
      toast.error(msg, { id: loadingToast });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!busy) {
          setOpen(o);
          if (!o) reset();
        }
      }}
    >
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Importar contatos via CSV</DialogTitle>
          <DialogDescription>
            Envie um arquivo .csv com seus contatos. Geocodificação acontecerá
            depois — esta importação é apenas de cadastro.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Template */}
          <a
            href="/contatos-modelo.csv"
            download
            className="flex items-center gap-3 p-3 rounded-lg border border-dashed border-border hover:bg-accent transition-colors text-sm"
          >
            <FileSpreadsheet className="h-5 w-5 text-brand-500" />
            <div className="flex-1">
              <p className="font-medium">Baixar planilha modelo</p>
              <p className="text-xs text-muted-foreground">
                CSV com cabeçalhos prontos pra preencher
              </p>
            </div>
            <Download className="h-4 w-4 text-muted-foreground" />
          </a>

          {/* File picker */}
          <label className="block">
            <span className="text-sm font-medium">Arquivo CSV</span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              disabled={busy}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setResult(null);
              }}
              className="mt-1.5 block w-full text-sm
                         file:mr-3 file:py-2 file:px-3 file:rounded-md
                         file:border-0 file:text-sm file:font-medium
                         file:bg-primary file:text-primary-foreground
                         hover:file:bg-primary/90 file:cursor-pointer
                         disabled:opacity-50"
            />
            {file && (
              <p className="mt-1 text-xs text-muted-foreground">
                {file.name} — {(file.size / 1024).toFixed(1)} KB
              </p>
            )}
          </label>

          {/* Resultado pos-import */}
          {result && <ImportSummary result={result} />}
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => {
              setOpen(false);
              reset();
            }}
          >
            {result ? "Fechar" : "Cancelar"}
          </Button>
          <Button onClick={handleImport} disabled={!file || busy}>
            {busy ? (
              <>
                <Loader2 className="animate-spin" />
                Importando...
              </>
            ) : (
              <>
                <Upload />
                Importar
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ImportSummary({ result }: { result: ImportResult }) {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="grid grid-cols-3 gap-3 text-center">
        <Stat label="Importados" value={result.imported} tone="emerald" />
        <Stat label="Pulados" value={result.skipped} tone="amber" />
        <Stat label="Total" value={result.total_rows} tone="slate" />
      </div>

      {result.errors.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            Ver {result.errors.length} erro(s)
          </summary>
          <ul className="mt-2 space-y-1 max-h-40 overflow-auto rounded-md border bg-muted/30 p-2 font-mono text-xs">
            {result.errors.map((e, i) => (
              <li key={i}>
                <span className="text-muted-foreground">Linha {e.row}:</span>{" "}
                {e.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "emerald" | "amber" | "slate";
}) {
  const colors = {
    emerald: "text-emerald-600",
    amber: "text-amber-600",
    slate: "text-slate-600",
  }[tone];
  return (
    <div>
      <p className={`text-2xl font-semibold ${colors}`}>{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
