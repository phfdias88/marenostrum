"use client";

/**
 * Endereço em cascata pro cadastro de contato:
 *   Estado (UF) → Município (base TSE, filtrado pela UF) → Bairro (base Censo
 *   do município; se não houver, o usuário digita livre).
 *
 * Controlado: recebe `value` e `onChange`. O pai (ContactFormDialog) guarda
 * esse pedaço fora do react-hook-form, igual faz com as tags.
 *
 * Fase 3 estende isto com um mini-mapa pra marcar a coordenada quando o
 * bairro é digitado livre (município sem bairro na base — ex: Seropédica).
 */
import { Loader2, MapPin, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { Page, TseMunicipality } from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type AddressValue = {
  state: string;
  city: string;
  neighborhood: string;
  latitude: number | null;
  longitude: number | null;
};

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export function AddressFields({
  value,
  onChange,
}: {
  value: AddressValue;
  onChange: (v: AddressValue) => void;
}) {
  const patch = (p: Partial<AddressValue>) => onChange({ ...value, ...p });

  // -------- Município (typeahead TSE filtrado pela UF) --------
  const [muniSearch, setMuniSearch] = useState("");
  const muniDeb = useDebounce(muniSearch, 300);
  const [muniItems, setMuniItems] = useState<TseMunicipality[]>([]);
  const [muniLoading, setMuniLoading] = useState(false);
  const [muniOpen, setMuniOpen] = useState(false);

  useEffect(() => {
    const q = muniDeb.trim();
    if (!value.state || q.length < 2) {
      setMuniItems([]);
      return;
    }
    setMuniLoading(true);
    const p = new URLSearchParams({ limit: "20", search: q, state: value.state });
    api<Page<TseMunicipality>>(`/v1/tse/municipalities?${p.toString()}`)
      .then((r) => setMuniItems(r.items))
      .catch(() => setMuniItems([]))
      .finally(() => setMuniLoading(false));
  }, [muniDeb, value.state]);

  // -------- Bairros do município (base Censo) --------
  const [nbList, setNbList] = useState<string[]>([]);
  const [nbOpen, setNbOpen] = useState(false);
  const nbBoxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!value.state || !value.city) {
      setNbList([]);
      return;
    }
    const p = new URLSearchParams({ uf: value.state, municipio: value.city });
    api<string[]>(`/v1/census/municipality-neighborhoods?${p.toString()}`)
      .then(setNbList)
      .catch(() => setNbList([]));
  }, [value.state, value.city]);

  // fecha dropdown de bairro ao clicar fora
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (nbBoxRef.current && !nbBoxRef.current.contains(e.target as Node)) {
        setNbOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const nbMatches =
    value.neighborhood.trim().length > 0
      ? nbList.filter((n) =>
          n.toLowerCase().includes(value.neighborhood.trim().toLowerCase()),
        )
      : nbList;
  // Bairro digitado que NÃO está na lista da base → caso "bairro livre".
  const isFreeNeighborhood =
    !!value.neighborhood.trim() &&
    nbList.length > 0 &&
    !nbList.some(
      (n) => n.toLowerCase() === value.neighborhood.trim().toLowerCase(),
    );

  return (
    <>
      {/* Estado */}
      <div>
        <Label className="mb-1.5 block">Estado (UF)</Label>
        <select
          value={value.state}
          onChange={(e) =>
            // troca de UF zera município e bairro
            onChange({
              state: e.target.value,
              city: "",
              neighborhood: "",
              latitude: null,
              longitude: null,
            })
          }
          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">Selecione…</option>
          {TSE_STATES.map((uf) => (
            <option key={uf} value={uf}>
              {uf}
            </option>
          ))}
        </select>
      </div>

      {/* Município */}
      <div className="relative">
        <Label className="mb-1.5 block">Município</Label>
        {value.city ? (
          <div className="flex items-center justify-between gap-2 h-10 px-3 rounded-md bg-background border border-primary/40">
            <span className="font-medium truncate">{value.city}</span>
            <button
              type="button"
              onClick={() => {
                patch({ city: "", neighborhood: "" });
                setMuniSearch("");
              }}
              className="text-muted-foreground hover:text-foreground shrink-0"
              aria-label="Trocar município"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
              <Input
                value={muniSearch}
                disabled={!value.state}
                onChange={(e) => {
                  setMuniSearch(e.target.value);
                  setMuniOpen(true);
                }}
                onFocus={() => setMuniOpen(true)}
                placeholder={value.state ? "Buscar município…" : "Escolha a UF primeiro"}
                className="pl-9"
              />
            </div>
            {muniOpen && (muniLoading || muniItems.length > 0) && (
              <div className="absolute z-30 mt-1 w-full rounded-md border bg-card shadow-lg max-h-56 overflow-auto divide-y divide-border">
                {muniLoading && (
                  <div className="p-2.5 text-center text-sm text-muted-foreground">
                    <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> buscando…
                  </div>
                )}
                {muniItems.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      patch({ city: m.name, neighborhood: "" });
                      setMuniOpen(false);
                      setMuniSearch("");
                    }}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-accent/50"
                  >
                    {m.name} <span className="text-muted-foreground">/{m.state}</span>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Bairro (sugestões do censo + livre) */}
      <div className="relative sm:col-span-2" ref={nbBoxRef}>
        <Label className="mb-1.5 block">Bairro</Label>
        <Input
          value={value.neighborhood}
          disabled={!value.city}
          onChange={(e) => {
            patch({ neighborhood: e.target.value });
            setNbOpen(true);
          }}
          onFocus={() => setNbOpen(true)}
          placeholder={
            !value.city
              ? "Escolha o município primeiro"
              : nbList.length
                ? "Digite ou escolha da lista…"
                : "Digite o bairro"
          }
        />
        {nbOpen && nbMatches.length > 0 && (
          <div className="absolute z-30 mt-1 w-full rounded-md border bg-card shadow-lg max-h-56 overflow-auto divide-y divide-border">
            {nbMatches.slice(0, 30).map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => {
                  patch({ neighborhood: n });
                  setNbOpen(false);
                }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-accent/50"
              >
                {n}
              </button>
            ))}
          </div>
        )}
        {isFreeNeighborhood && (
          <p className="mt-1 text-xs text-amber-500 flex items-center gap-1">
            <MapPin className="w-3 h-3" />
            Bairro fora da base do município — confira a grafia ou cadastre
            assim mesmo.
          </p>
        )}
      </div>
    </>
  );
}
