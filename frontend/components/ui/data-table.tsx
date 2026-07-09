"use client";

/**
 * DataTable generica baseada em @tanstack/react-table.
 * - Pagina server-side: o componente exibe controles mas NAO faz slicing local;
 *   ele dispara `onPageChange` para o pai recarregar da API.
 * - Usa o Table UI do shadcn para consistencia visual.
 */
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type DataTableProps<TData, TValue> = {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  total: number;
  pageSize: number;
  pageIndex: number;
  onPageChange: (next: number) => void;
  isLoading?: boolean;
  emptyMessage?: string;
  /** CTA opcional exibido junto ao estado vazio (ex.: abrir dialog de criação). */
  emptyAction?: { label: string; onClick: () => void };
};

// Larguras variadas pros skeletons parecerem conteudo real (ciclo deterministico).
const SKELETON_WIDTHS = ["w-3/4", "w-1/2", "w-2/3", "w-1/3", "w-5/6"];

export function DataTable<TData, TValue>({
  columns,
  data,
  total,
  pageSize,
  pageIndex,
  onPageChange,
  isLoading,
  emptyMessage = "Nenhum registro.",
  emptyAction,
}: DataTableProps<TData, TValue>) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    pageCount: Math.max(1, Math.ceil(total / pageSize)),
  });

  const start = total === 0 ? 0 : pageIndex * pageSize + 1;
  const end = Math.min((pageIndex + 1) * pageSize, total);
  const lastPage = Math.max(0, Math.ceil(total / pageSize) - 1);

  return (
    <div className="space-y-3">
      <div className="rounded-xl border bg-card">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="hover:bg-transparent">
                {hg.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>

          <TableBody>
            {isLoading ? (
              // Skeleton com o mesmo nº de linhas da pagina: estabiliza a
              // altura da tabela entre paginacoes (sem "pulo" de layout).
              Array.from({ length: pageSize || 8 }).map((_, rowIdx) => (
                <TableRow key={`skeleton-${rowIdx}`}>
                  {columns.map((_, colIdx) => (
                    <TableCell key={colIdx}>
                      <Skeleton
                        className={`h-4 ${
                          SKELETON_WIDTHS[
                            (rowIdx + colIdx) % SKELETON_WIDTHS.length
                          ]
                        }`}
                      />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="text-center text-muted-foreground py-10"
                >
                  <p>{emptyMessage}</p>
                  {emptyAction && (
                    <Button
                      size="sm"
                      className="mt-3"
                      onClick={emptyAction.onClick}
                    >
                      {emptyAction.label}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Paginacao */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <div>
          {total === 0
            ? "0 registros"
            : `Mostrando ${start}–${end} de ${total}`}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(pageIndex - 1)}
            disabled={pageIndex <= 0 || isLoading}
          >
            <ChevronLeft />
            Anterior
          </Button>
          <span className="px-2">
            Pag. {pageIndex + 1} de {lastPage + 1}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(pageIndex + 1)}
            disabled={pageIndex >= lastPage || isLoading}
          >
            Próxima
            <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  );
}
