"use client";

/**
 * /dashboard/map — Mapa da Campanha.
 *
 * Layout: mapa à esquerda (bolhas por bairro/local de votação), filtros +
 * gráfico de barras à direita. Métrica alterna contatos ↔ demandas; agrupa
 * por bairro ↔ local de votação; filtros por UF, município, bairro, tipo, tag.
 *
 * CampaignMap é importado via next/dynamic({ssr:false}) — Leaflet usa window.
 */
import dynamic from "next/dynamic";
import { BarChart3, Loader2, MapPinned, Users, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { MapGroup } from "@/components/map/CampaignMap";
import { CONTACT_TYPE_LABELS, TSE_STATES, type ContactTag, type ContactType } from "@/lib/types";
import { cn } from "@/lib/utils";

const CampaignMap = dynamic(() => import("@/components/map/CampaignMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full grid place-items-center text-muted-foreground">
      <Loader2 className="w-5 h-5 animate-spin mr-2" /> carregando mapa…
    </div>
  ),
});

const numberFmt = new Intl.NumberFormat("pt-BR");

type Metric = "contacts" | "demands";
type GroupBy = "neighborhood" | "voting_place";

function useDebounce<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export default function MapPage() {
  const [metric, setMetric] = useState<Metric>("contacts");
  const [groupBy, setGroupBy] = useState<GroupBy>("neighborhood");
  const [uf, setUf] = useState("");
  const [city, setCity] = useState("");
  const [neighborhood, setNeighborhood] = useState("");
  const [type, setType] = useState("");
  const [tag, setTag] = useState("");

  const cityD = useDebounce(city, 400);
  const nbD = useDebounce(neighborhood, 400);

  const [groups, setGroups] = useState<MapGroup[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<ContactTag[]>("/v1/contacts/tags")
      .then((r) => setTags(r.map((t) => t.tag)))
      .catch(() => setTags([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams({ metric, group_by: groupBy });
    if (uf) p.set("state", uf);
    if (cityD.trim()) p.set("city", cityD.trim());
    if (nbD.trim()) p.set("neighborhood", nbD.trim());
    if (type) p.set("type", type);
    if (tag) p.set("tag", tag);
    api<MapGroup[]>(`/v1/contacts/map-aggregate?${p.toString()}`)
      .then(setGroups)
      .catch(() => setGroups([]))
      .finally(() => setLoading(false));
  }, [metric, groupBy, uf, cityD, nbD, type, tag]);

  const total = useMemo(() => groups.reduce((s, g) => s + g.count, 0), [groups]);
  const max = useMemo(() => Math.max(1, ...groups.map((g) => g.count)), [groups]);
  const top = groups.slice(0, 15);
  const noCoords = groups.filter((g) => g.lat == null).reduce((s, g) => s + g.count, 0);

  const metricLabel = metric === "contacts" ? "contatos" : "demandas";
  const groupLabel = groupBy === "neighborhood" ? "bairro" : "local de votação";

  const hasFilters = uf || city || neighborhood || type || tag;
  function clearFilters() {
    setUf(""); setCity(""); setNeighborhood(""); setType(""); setTag("");
  }

  return (
    <div className="flex flex-col lg:flex-row gap-4 p-3 sm:p-4 h-[calc(100dvh-3.5rem-64px-env(safe-area-inset-bottom))] md:h-[calc(100dvh-3.5rem)]">
      {/* Mapa */}
      <div className="lg:flex-1 min-h-[320px] rounded-xl overflow-hidden border border-border relative">
        <CampaignMap groups={groups} metricLabel={metricLabel} />
        {loading && (
          <div className="absolute top-3 left-3 z-[500] bg-card/90 border border-border rounded-md px-2.5 py-1 text-xs flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" /> atualizando…
          </div>
        )}
      </div>

      {/* Painel: filtros + gráfico */}
      <aside className="lg:w-[360px] shrink-0 flex flex-col gap-3 overflow-y-auto">
        {/* Métrica + agrupamento */}
        <div className="rounded-xl border border-border bg-card p-3 space-y-3">
          <Toggle
            label="Visualizar"
            value={metric}
            onChange={(v) => setMetric(v as Metric)}
            options={[
              { value: "contacts", label: "Contatos", icon: <Users className="w-3.5 h-3.5" /> },
              { value: "demands", label: "Demandas", icon: <BarChart3 className="w-3.5 h-3.5" /> },
            ]}
          />
          <Toggle
            label="Agrupar por"
            value={groupBy}
            onChange={(v) => setGroupBy(v as GroupBy)}
            options={[
              { value: "neighborhood", label: "Bairro" },
              { value: "voting_place", label: "Local de votação" },
            ]}
          />
        </div>

        {/* Filtros */}
        <div className="rounded-xl border border-border bg-card p-3 space-y-2.5">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-wider text-muted-foreground font-medium">
              Filtros
            </p>
            {hasFilters && (
              <button
                onClick={clearFilters}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                <X className="w-3 h-3" /> limpar
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Select label="UF" value={uf} onChange={setUf} options={[["", "Todas"], ...TSE_STATES.map((s) => [s, s] as [string, string])]} />
            <Select
              label="Tipo"
              value={type}
              onChange={setType}
              options={[["", "Todos"], ...(Object.entries(CONTACT_TYPE_LABELS) as [ContactType, string][]).map(([v, l]) => [v, l] as [string, string])]}
            />
          </div>
          <TextField label="Município" value={city} onChange={setCity} placeholder="ex: Rio de Janeiro" />
          <TextField label="Bairro" value={neighborhood} onChange={setNeighborhood} placeholder="ex: Copacabana" />
          {tags.length > 0 && (
            <Select label="Tag" value={tag} onChange={setTag} options={[["", "Todas"], ...tags.map((t) => [t, t] as [string, string])]} />
          )}
        </div>

        {/* Gráfico de barras */}
        <div className="rounded-xl border border-border bg-card p-3 flex-1 min-h-[200px]">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs uppercase tracking-wider text-muted-foreground font-medium flex items-center gap-1.5">
              <MapPinned className="w-3.5 h-3.5" /> {metricLabel} por {groupLabel}
            </p>
            <span className="text-xs text-muted-foreground tabular-nums">
              {numberFmt.format(total)} no total
            </span>
          </div>
          {top.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              {loading ? "Carregando…" : "Nenhum dado com os filtros atuais."}
            </p>
          ) : (
            <ul className="space-y-2">
              {top.map((g) => (
                <li key={g.key}>
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate" title={g.key}>
                      {g.key}
                      {g.lat == null && (
                        <span className="text-[10px] text-muted-foreground ml-1">(sem mapa)</span>
                      )}
                    </span>
                    <span className="font-mono text-xs shrink-0 tabular-nums">{numberFmt.format(g.count)}</span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-muted/50 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-amber-300 via-primary to-amber-500 transition-[width] duration-500"
                      style={{ width: `${(g.count / max) * 100}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
          {noCoords > 0 && (
            <p className="text-[11px] text-muted-foreground mt-3 pt-2 border-t border-border">
              {numberFmt.format(noCoords)} {metricLabel} sem localização não
              aparecem como bolha (cadastre o endereço/coordenada).
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}

// ----------------------------------------------------- subcomponentes

function Toggle({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string; icon?: React.ReactNode }[];
}) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">{label}</p>
      <div className="flex gap-1 bg-background border border-border rounded-md p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 text-sm rounded transition-colors",
              value === o.value
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.icon}
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
      />
    </label>
  );
}
