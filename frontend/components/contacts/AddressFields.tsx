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
import dynamic from "next/dynamic";
import { Loader2, MapPin, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { Page, TseMunicipality } from "@/lib/types";
import { TSE_STATES } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const CoordinatePicker = dynamic(
  () => import("@/components/map/CoordinatePicker"),
  {
    ssr: false,
    loading: () => (
      <div className="h-[220px] grid place-items-center rounded-md bg-muted/40 text-sm text-muted-foreground">
        carregando mapa…
      </div>
    ),
  },
);

// Centro aproximado de cada UF — só pra dar um zoom inicial no mapa de
// coordenada (o usuário clica no ponto exato). Fallback: centro do Brasil.
const UF_CENTER: Record<string, [number, number]> = {
  AC: [-9.0, -70.5], AL: [-9.6, -36.6], AM: [-3.9, -63.0], AP: [1.4, -51.8],
  BA: [-12.6, -41.7], CE: [-5.1, -39.3], DF: [-15.8, -47.8], ES: [-19.6, -40.3],
  GO: [-16.0, -49.5], MA: [-5.2, -45.2], MG: [-18.5, -44.5], MS: [-20.5, -54.6],
  MT: [-12.9, -55.9], PA: [-4.0, -52.5], PB: [-7.1, -36.8], PE: [-8.4, -37.9],
  PI: [-7.5, -42.5], PR: [-24.6, -51.6], RJ: [-22.3, -42.7], RN: [-5.6, -36.6],
  RO: [-10.9, -63.0], RR: [2.1, -61.4], RS: [-30.0, -53.5], SC: [-27.2, -50.5],
  SE: [-10.6, -37.4], SP: [-22.2, -48.7], TO: [-10.2, -48.3],
};
const BR_CENTER: [number, number] = [-15.8, -47.9];

export type AddressValue = {
  state: string;
  city: string;
  neighborhood: string;
  votingPlace: string;
  latitude: number | null;
  longitude: number | null;
};

type VotingPlace = {
  name: string;
  neighborhood: string | null;
  address: string | null;
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
  onCoordMissingChange,
}: {
  value: AddressValue;
  onChange: (v: AddressValue) => void;
  // Avisa o formulário quando o bairro é livre e ainda falta marcar o ponto
  // no mapa (coordenada obrigatória só nesse caso).
  onCoordMissingChange?: (missing: boolean) => void;
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

  // -------- Centro do município (pra centralizar o mini-mapa) --------
  // Sem isso o mapa abria no centro da UF (ex: RJ → montanhas, longe do
  // município). Buscamos a média das coordenadas dos locais de votação do TSE.
  const [muniCenter, setMuniCenter] = useState<[number, number] | null>(null);

  useEffect(() => {
    setMuniCenter(null);
    if (!value.state || !value.city) return;
    const p = new URLSearchParams({ state: value.state, municipio: value.city });
    api<{ lat: number | null; lng: number | null }>(
      `/v1/tse/municipality-center?${p.toString()}`,
    )
      .then((c) => {
        if (c.lat != null && c.lng != null) setMuniCenter([c.lat, c.lng]);
      })
      .catch(() => setMuniCenter(null));
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

  const nbQuery = value.neighborhood.trim().toLowerCase();
  const nbMatches =
    nbQuery.length > 0
      ? nbList.filter((n) => n.toLowerCase().includes(nbQuery))
      : nbList;
  // Bairro digitado que NÃO casa com nenhum da base (base vazia ou nome livre,
  // ex: Seropédica / "KM 32") → exige marcar a coordenada no mapa.
  const needsCoord = nbQuery.length > 0 && nbMatches.length === 0;
  const hasCoord = value.latitude != null && value.longitude != null;
  // Município sem bairros na base (ex: Seropédica = distrito único): a lista
  // vem vazia ou só com o nome do próprio município. Avisamos que é digitar
  // livre + marcar no mapa, pra não esperar uma lista que não existe.
  const noRealBairros =
    !!value.city &&
    nbList.filter((n) => n.toLowerCase() !== value.city.toLowerCase()).length === 0;
  // Sugestões = matches da base, sem o nome do próprio município (que aparece
  // como "distrito único" em cidades sem bairros).
  const nbSuggestions = nbMatches.filter(
    (n) => n.toLowerCase() !== value.city.toLowerCase(),
  );

  // Reporta pro formulário: bairro livre sem coordenada = bloqueia o salvar.
  useEffect(() => {
    onCoordMissingChange?.(needsCoord && !hasCoord);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsCoord, hasCoord]);

  // -------- Local de votação (base TSE do município) --------
  const [vpSearch, setVpSearch] = useState("");
  const vpDeb = useDebounce(vpSearch, 300);
  const [vpItems, setVpItems] = useState<VotingPlace[]>([]);
  const [vpOpen, setVpOpen] = useState(false);
  const vpBoxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!value.state || !value.city) {
      setVpItems([]);
      return;
    }
    const p = new URLSearchParams({ state: value.state, municipio: value.city });
    if (vpDeb.trim()) p.set("search", vpDeb.trim());
    api<VotingPlace[]>(`/v1/tse/voting-places?${p.toString()}`)
      .then(setVpItems)
      .catch(() => setVpItems([]));
  }, [vpDeb, value.state, value.city]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (vpBoxRef.current && !vpBoxRef.current.contains(e.target as Node)) {
        setVpOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <>
      {/* Estado */}
      <div>
        <Label className="mb-1.5 block">Estado (UF)</Label>
        <select
          value={value.state}
          onChange={(e) =>
            // troca de UF zera município, bairro e local de votação
            onChange({
              state: e.target.value,
              city: "",
              neighborhood: "",
              votingPlace: "",
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
                patch({ city: "", neighborhood: "", votingPlace: "" });
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
                      patch({ city: m.name, neighborhood: "", votingPlace: "" });
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
              : noRealBairros
                ? "Digite o nome do bairro"
                : "Digite ou escolha da lista…"
          }
        />
        {noRealBairros && !value.neighborhood.trim() && (
          <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
            <MapPin className="w-3 h-3" />
            Este município não tem bairros na base do IBGE. Digite o nome e
            marque a localização no mapa.
          </p>
        )}
        {nbOpen && nbSuggestions.length > 0 && (
          <div className="absolute z-30 mt-1 w-full rounded-md border bg-card shadow-lg max-h-56 overflow-auto divide-y divide-border">
            {nbSuggestions.slice(0, 30).map((n) => (
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
        {needsCoord && (
          <p className="mt-1 text-xs text-amber-500 flex items-center gap-1">
            <MapPin className="w-3 h-3" />
            Bairro fora da base: marque a localização no mapa abaixo
            (obrigatório).
          </p>
        )}
      </div>

      {/* Mapa de coordenada — só quando o bairro é livre (fora da base). */}
      {needsCoord && (
        <div className="sm:col-span-2">
          <Label className="mb-1.5 block">
            Localização no mapa{" "}
            {hasCoord ? (
              <span className="text-emerald-500 font-normal">
                ✓ ponto marcado
              </span>
            ) : (
              <span className="text-amber-500 font-normal">
                clique pra marcar
              </span>
            )}
          </Label>
          <CoordinatePicker
            value={hasCoord ? { lat: value.latitude!, lng: value.longitude! } : null}
            // Centro do município (TSE) quando já carregou; senão centro da UF.
            center={muniCenter ?? UF_CENTER[value.state] ?? BR_CENTER}
            zoom={muniCenter ? 13 : 9}
            onPick={(lat, lng) => patch({ latitude: lat, longitude: lng })}
          />
          {hasCoord && (
            <p className="mt-1 text-[11px] text-muted-foreground">
              {value.latitude!.toFixed(5)}, {value.longitude!.toFixed(5)} ·
              clique de novo pra reposicionar
            </p>
          )}
        </div>
      )}

      {/* Local de votação (base TSE do município) */}
      <div className="relative sm:col-span-2" ref={vpBoxRef}>
        <Label className="mb-1.5 block">Local de votação</Label>
        {value.votingPlace ? (
          <div className="flex items-center justify-between gap-2 min-h-10 px-3 py-2 rounded-md bg-background border border-primary/40">
            <span className="font-medium text-sm truncate">{value.votingPlace}</span>
            <button
              type="button"
              onClick={() => {
                patch({ votingPlace: "" });
                setVpSearch("");
              }}
              className="text-muted-foreground hover:text-foreground shrink-0"
              aria-label="Trocar local de votação"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
              <Input
                value={vpSearch}
                disabled={!value.city}
                onChange={(e) => {
                  setVpSearch(e.target.value);
                  setVpOpen(true);
                }}
                onFocus={() => setVpOpen(true)}
                placeholder={
                  value.city
                    ? "Buscar onde o contato vota (escola, igreja…)"
                    : "Escolha o município primeiro"
                }
                className="pl-9"
              />
            </div>
            {vpOpen && vpItems.length > 0 && (
              <div className="absolute z-30 mt-1 w-full rounded-md border bg-card shadow-lg max-h-56 overflow-auto divide-y divide-border">
                {vpItems.map((p, i) => (
                  <button
                    key={`${p.name}:${i}`}
                    type="button"
                    onClick={() => {
                      patch({ votingPlace: p.name });
                      setVpOpen(false);
                      setVpSearch("");
                    }}
                    className="w-full text-left px-3 py-2 hover:bg-accent/50"
                  >
                    <p className="text-sm font-medium truncate">{p.name}</p>
                    {p.neighborhood && (
                      <p className="text-xs text-muted-foreground truncate">
                        {p.neighborhood}
                      </p>
                    )}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
