"use client";

/**
 * UnmappedLocations — disclosure com os Locais de Votação SEM coordenada válida
 * de um município (os que o pipeline de enriquecimento ViaCEP→Nominatim tenta
 * recuperar). Busca sob demanda (só quando expandido).
 *
 * geo_source:
 *   'unmapped' = sem coordenada nenhuma (vermelho)
 *   'centroid' = parkado no centro do município, impreciso (âmbar)
 */
import { AlertTriangle, ChevronDown, Loader2, MapPinOff } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";

const numberFmt = new Intl.NumberFormat("pt-BR");

type UnmappedItem = {
  id: string;
  name: string;
  neighborhood: string | null;
  address: string | null;
  geo_source: string;
  electors: number | null;
};
type UnmappedResp = { summary: Record<string, number>; items: UnmappedItem[] };

export function UnmappedLocations({
  municipalityId,
  year = 2024,
}: {
  municipalityId: string;
  year?: number;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<UnmappedResp | null>(null);
  const [loading, setLoading] = useState(false);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && !data && !loading) {
      setLoading(true);
      api<UnmappedResp>(
        `/v1/tse/voting-places/unmapped?municipality_id=${municipalityId}&year=${year}`,
      )
        .then(setData)
        .catch(() => setData({ summary: {}, items: [] }))
        .finally(() => setLoading(false));
    }
  };

  const count = data ? data.items.length : null;
  const unmappedN = data?.summary?.unmapped ?? 0;
  const centroidN = data?.summary?.centroid ?? 0;

  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-400/5">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between gap-2 p-2.5 text-xs"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-1.5 text-amber-500 font-medium">
          <MapPinOff className="w-3.5 h-3.5" /> Locais não mapeados
          {count != null && <span className="text-muted-foreground">({count})</span>}
        </span>
        <ChevronDown
          className={`w-4 h-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="px-2.5 pb-2.5">
          {loading ? (
            <div className="py-4 text-center">
              <Loader2 className="w-4 h-4 animate-spin mx-auto text-muted-foreground" />
            </div>
          ) : !data || data.items.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">
              Todos os locais deste município estão mapeados. 🎉
            </p>
          ) : (
            <>
              <p className="text-[11px] text-muted-foreground mb-2 leading-relaxed">
                {unmappedN > 0 && <>{numberFmt.format(unmappedN)} sem coordenada</>}
                {unmappedN > 0 && centroidN > 0 && " · "}
                {centroidN > 0 && (
                  <>{numberFmt.format(centroidN)} no centro do município (imprecisos)</>
                )}
                . O enriquecimento (ViaCEP→Nominatim) tenta recuperar a coordenada
                real destes.
              </p>
              <ul className="rounded border border-border divide-y divide-border max-h-48 overflow-auto text-xs bg-card">
                {data.items.map((p) => (
                  <li key={p.id} className="p-2">
                    <p className="font-medium truncate flex items-center gap-1.5">
                      {p.geo_source === "unmapped" ? (
                        <AlertTriangle className="w-3 h-3 text-red-500 shrink-0" />
                      ) : (
                        <MapPinOff className="w-3 h-3 text-amber-500 shrink-0" />
                      )}
                      <span className="truncate">{p.name}</span>
                    </p>
                    <p className="text-muted-foreground truncate">
                      {p.neighborhood || p.address || "—"}
                    </p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
