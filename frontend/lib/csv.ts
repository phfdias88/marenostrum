/**
 * Geração e download de CSV no cliente (sem backend).
 * - separador ";" (Excel pt-BR usa ; por padrão)
 * - BOM UTF-8 pra acentos abrirem certo no Excel
 * - escapa aspas/; /quebras de linha
 */
function escapeCell(v: unknown): string {
  const s = v == null ? "" : String(v);
  if (/[";\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function downloadCsv(
  filename: string,
  columns: { key: string; label: string }[],
  rows: Record<string, unknown>[],
): void {
  const header = columns.map((c) => escapeCell(c.label)).join(";");
  const body = rows
    .map((r) => columns.map((c) => escapeCell(r[c.key])).join(";"))
    .join("\r\n");
  const csv = "﻿" + header + "\r\n" + body; // BOM + conteúdo

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
