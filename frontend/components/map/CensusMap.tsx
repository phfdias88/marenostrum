"use client";

/**
 * Mapa coroplético de setores/municípios (IBGE Censo 2022).
 * Renderiza GeoJSON colorido por um indicador, com legenda, tooltip no hover
 * e destaque do selecionado. Client-only (Leaflet usa window) — importar via
 * next/dynamic({ssr:false}).
 */
import { useEffect, useMemo, useRef, type MutableRefObject } from "react";
import L from "leaflet";
import { GeoJSON, MapContainer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { ThemedTileLayer } from "./ThemedTileLayer";

export type CensusIndicator =
  | "populacao"
  | "densidade_hab_km2"
  | "domicilios"
  | "media_moradores"
  | "taxa_alfabetizacao"
  | "pct_pretos_pardos"
  | "renda_media"
  | "pct_bolsa_familia"
  | "pct_cadunico"
  | "pib_per_capita"
  | "idhm"
  | "ideb_anos_iniciais"
  | "ideb_anos_finais"
  | "pct_agua_rede"
  | "pct_esgoto_adequado"
  | "pct_lixo_coletado";

type FC = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: unknown;
    properties: Record<string, number | string | null>;
  }>;
};

// Rampa sequencial quente (ouro → carmim). A cor mais clara é um ouro nítido
// (não creme) pra não sumir no tile claro do mapa.
const RAMP = ["#fdd692", "#f9bb5b", "#f09a3c", "#e0742e", "#c44a2a", "#8f1d2c"];
const NO_DATA = "#9aa0a6";

const numFmt = new Intl.NumberFormat("pt-BR");
const FMT: Record<CensusIndicator, (v: number) => string> = {
  populacao: (v) => `${numFmt.format(Math.round(v))} hab`,
  domicilios: (v) => `${numFmt.format(Math.round(v))} domic.`,
  densidade_hab_km2: (v) => `${numFmt.format(Math.round(v))} hab/km²`,
  media_moradores: (v) => `${v.toFixed(2).replace(".", ",")} /domic.`,
  taxa_alfabetizacao: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pct_pretos_pardos: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  renda_media: (v) => `R$ ${numFmt.format(Math.round(v))}`,
  pct_bolsa_familia: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pct_cadunico: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pib_per_capita: (v) => `R$ ${numFmt.format(Math.round(v))}`,
  idhm: (v) => v.toFixed(3).replace(".", ","),
  ideb_anos_iniciais: (v) => v.toFixed(1).replace(".", ","),
  ideb_anos_finais: (v) => v.toFixed(1).replace(".", ","),
  pct_agua_rede: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pct_esgoto_adequado: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  pct_lixo_coletado: (v) => `${v.toFixed(1).replace(".", ",")}%`,
};
const LABEL: Record<CensusIndicator, string> = {
  populacao: "População",
  domicilios: "Domicílios",
  densidade_hab_km2: "Densidade (hab/km²)",
  media_moradores: "Moradores / domicílio",
  taxa_alfabetizacao: "Alfabetização 15+ (%)",
  pct_pretos_pardos: "Cor ou raça — pretos e pardos (%)",
  renda_media: "Renda média domiciliar (R$, 2010)",
  pct_bolsa_familia: "Bolsa Família (% domicílios)",
  pct_cadunico: "CadÚnico (% domicílios)",
  pib_per_capita: "PIB per capita (R$)",
  idhm: "IDHM (2010)",
  ideb_anos_iniciais: "IDEB anos iniciais (2023)",
  ideb_anos_finais: "IDEB anos finais (2023)",
  pct_agua_rede: "Água por rede (% domic.)",
  pct_esgoto_adequado: "Esgoto adequado (% domic.)",
  pct_lixo_coletado: "Lixo coletado (% domic.)",
};

function classIndex(v: number | null, breaks: number[]): number {
  if (v == null) return -1;
  for (let i = breaks.length - 1; i >= 0; i--) if (v >= breaks[i]) return i;
  return 0;
}
function colorFor(v: number | null, breaks: number[]): string {
  const i = classIndex(v, breaks);
  return i < 0 ? NO_DATA : RAMP[i];
}

// Quebras por quantis (6 classes).
function computeBreaks(values: number[]): number[] {
  const v = values.filter((x) => x != null && x > 0).sort((a, b) => a - b);
  if (v.length === 0) return [0, 1, 2, 3, 4, 5];
  const q = (p: number) => v[Math.min(v.length - 1, Math.floor(p * v.length))];
  return [Math.min(...v), q(0.2), q(0.4), q(0.6), q(0.8), q(0.95)];
}

function FitBounds({ data }: { data: FC }) {
  const map = useMap();
  useEffect(() => {
    if (!data.features.length) return;
    const layer = L.geoJSON(data as unknown as GeoJSON.GeoJsonObject);
    const b = layer.getBounds();
    if (b.isValid()) map.fitBounds(b, { padding: [16, 16] });
  }, [data, map]);
  return null;
}

// Dá zoom + destaca um GRUPO de setores (focusIds = lista de cd_setor).
// Serve tanto p/ 1 setor (clique) quanto p/ um bairro inteiro (busca).
function FocusController({
  focusIds,
  reg,
  baseStyleRef,
  indicatorRef,
}: {
  focusIds?: string[] | null;
  reg: MutableRefObject<Map<string, L.Path>>;
  baseStyleRef: MutableRefObject<(v: number | null) => object>;
  indicatorRef: MutableRefObject<string>;
}) {
  const map = useMap();
  const prevRef = useRef<L.Path[]>([]);
  const fingerprint = (focusIds ?? []).join(",");
  useEffect(() => {
    // restaura o grupo anterior
    for (const lyr of prevRef.current) {
      const pf = (lyr as unknown as {
        feature?: { properties?: Record<string, number | string | null> };
      }).feature?.properties;
      lyr.setStyle(baseStyleRef.current((pf?.[indicatorRef.current] ?? null) as number | null));
    }
    prevRef.current = [];
    if (!focusIds || focusIds.length === 0) return;
    const layers = focusIds.map((id) => reg.current.get(id)).filter(Boolean) as L.Path[];
    if (!layers.length) return;
    let bounds: L.LatLngBounds | null = null;
    for (const lyr of layers) {
      lyr.setStyle({ weight: 1.4, color: "#e8c879", fillOpacity: 0.95 });
      lyr.bringToFront();
      const b = (lyr as unknown as { getBounds?: () => L.LatLngBounds }).getBounds?.();
      if (b && b.isValid()) bounds = bounds ? bounds.extend(b) : L.latLngBounds(b.getSouthWest(), b.getNorthEast());
    }
    if (bounds && bounds.isValid()) map.fitBounds(bounds, { maxZoom: 15, padding: [40, 40] });
    prevRef.current = layers;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fingerprint]);
  return null;
}

export function CensusMap({
  data,
  indicator,
  onSelect,
  focusIds,
  dataVersion,
}: {
  data: FC;
  indicator: CensusIndicator;
  onSelect: (props: Record<string, number | string | null>) => void;
  focusIds?: string[] | null;
  // Muda quando a MALHA muda (setor/distrito/bairro) com os MESMOS setores —
  // força recriar o layer (senão a repintura in-place lê as props antigas).
  dataVersion?: string;
}) {
  const breaks = useMemo(
    () => computeBreaks(data.features.map((f) => f.properties[indicator] as number)),
    [data, indicator],
  );
  const selectedRef = useRef<L.Path | null>(null);
  const layerReg = useRef<Map<string, L.Path>>(new Map());
  const geoRef = useRef<L.GeoJSON | null>(null);
  const fmt = FMT[indicator];
  // key NÃO inclui o indicador: trocar de indicador repinta os polígonos
  // in-place (setStyle) em vez de recriar o layer inteiro (caro no Rio).
  const key = `${String(data.features[0]?.properties?.cd_setor ?? data.features[0]?.properties?.cd_mun ?? "")}-${data.features.length}-${dataVersion ?? ""}`;

  const baseStyle = (v: number | null) => ({
    fillColor: colorFor(v, breaks),
    weight: 0.6,
    color: "#7a5b1e",
    fillOpacity: v == null ? 0.55 : 0.86,
  });
  // refs: handlers de evento e FocusController leem sempre o estado ATUAL
  // (sem stale-closure — os layers não são recriados na troca de indicador).
  const baseStyleRef = useRef(baseStyle);
  baseStyleRef.current = baseStyle;
  const indicatorRef = useRef(indicator);
  indicatorRef.current = indicator;

  // Tooltip rico (hover já resolve): setor mostra distrito·bairro + pop + domic.
  const tipHtml = (p: Record<string, number | string | null>, v: number | null) => {
    if (p.cd_setor != null) {
      const head =
        [p.nm_dist, p.nm_bairro].filter(Boolean).join(" · ") || `Setor ${p.cd_setor}`;
      return (
        `<div style="font-weight:700;margin-bottom:3px">${head}</div>` +
        `<div style="opacity:.9">${numFmt.format(Number(p.populacao || 0))} hab · ${numFmt.format(Number(p.domicilios || 0))} domic.</div>` +
        `<div style="opacity:.65;font-size:10px;margin-top:2px">${LABEL[indicator]}: ${v != null ? fmt(v) : "sem dado"}</div>`
      );
    }
    return (
      `<div style="font-weight:700;margin-bottom:2px">${p.nm_mun || ""}</div>` +
      `<div style="opacity:.9">${LABEL[indicator]}: ${v != null ? fmt(v) : "sem dado"}</div>`
    );
  };
  const tipHtmlRef = useRef(tipHtml);
  tipHtmlRef.current = tipHtml;

  // Troca de indicador → repinta cada polígono e atualiza tooltips já criados,
  // sem destruir/recriar os (até 13k) layers.
  useEffect(() => {
    const g = geoRef.current;
    if (!g) return;
    g.eachLayer((lyr) => {
      const f = (lyr as unknown as {
        feature?: { properties?: Record<string, number | string | null> };
      }).feature;
      const p = f?.properties ?? {};
      const v = (p[indicator] ?? null) as number | null;
      if ((lyr as L.Path) !== selectedRef.current) (lyr as L.Path).setStyle(baseStyle(v));
      const withTip = lyr as unknown as {
        getTooltip?: () => unknown;
        setTooltipContent?: (html: string) => void;
      };
      if (withTip.getTooltip?.()) withTip.setTooltipContent?.(tipHtml(p, v));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indicator, breaks]);

  // Existe algum setor/município sem valor pro indicador atual? (ex.: densidade
  // num setor sem população). Aí mostramos "sem dado" na legenda.
  const hasNoData = data.features.some((f) => f.properties[indicator] == null);

  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={[-22.3, -42.7]}
        zoom={9}
        style={{ height: "100%", width: "100%", background: "#0b0b0c" }}
        scrollWheelZoom
        preferCanvas
      >
        <ThemedTileLayer />
        <FitBounds data={data} />
        <FocusController
          focusIds={focusIds}
          reg={layerReg}
          baseStyleRef={baseStyleRef}
          indicatorRef={indicatorRef}
        />
        <GeoJSON
          key={key}
          ref={geoRef as never}
          data={data as unknown as GeoJSON.GeoJsonObject}
          style={(feature) => baseStyle((feature?.properties?.[indicator] ?? null) as number | null)}
          onEachFeature={(feature, layer) => {
            const p = feature.properties as Record<string, number | string | null>;
            const path = layer as L.Path;
            const regKey = String(p.cd_setor ?? p.cd_mun ?? "");
            if (regKey) layerReg.current.set(regKey, path);
            // Valor do indicador ATUAL (via ref — o layer sobrevive à troca).
            const curV = () => (p[indicatorRef.current] ?? null) as number | null;
            // Tooltip preguiçoso: só cria o objeto no 1º hover (render mais leve).
            let tipBound = false;
            layer.on({
              click: () => {
                if (selectedRef.current && selectedRef.current !== path) {
                  const prevFeat = (selectedRef.current as unknown as {
                    feature?: { properties?: Record<string, number | string | null> };
                  }).feature;
                  const pv = (prevFeat?.properties?.[indicatorRef.current] ?? null) as number | null;
                  selectedRef.current.setStyle(baseStyleRef.current(pv));
                }
                path.setStyle({ weight: 2.5, color: "#e8c879", fillOpacity: 0.95 });
                path.bringToFront();
                selectedRef.current = path;
                onSelect(p);
              },
              mouseover: () => {
                if (!tipBound) {
                  layer.bindTooltip(tipHtmlRef.current(p, curV()), {
                    sticky: true,
                    direction: "top",
                    className: "mn-tip",
                  });
                  tipBound = true;
                  layer.openTooltip();
                }
                if (path !== selectedRef.current) path.setStyle({ weight: 1.6, color: "#fff", fillOpacity: 0.92 });
              },
              mouseout: () => {
                if (path !== selectedRef.current) path.setStyle(baseStyleRef.current(curV()));
              },
            });
          }}
        />
      </MapContainer>

      {/* Legenda */}
      <div className="absolute bottom-3 right-3 z-[400] rounded-xl bg-black/75 backdrop-blur-md px-3.5 py-2.5 border border-amber-200/15 shadow-2xl shadow-black/50 text-[11px] text-white ring-1 ring-white/5">
        <p className="font-semibold mb-2 tracking-wide text-amber-100/90">{LABEL[indicator]}</p>
        <ul className="space-y-1">
          {RAMP.map((c, i) => (
            <li key={i} className="flex items-center gap-2">
              <span
                className="inline-block w-4 h-3.5 rounded ring-1 ring-white/15"
                style={{ background: c, boxShadow: `0 0 6px ${c}55` }}
              />
              <span className="tabular-nums text-white/85">
                {i === RAMP.length - 1
                  ? `≥ ${fmt(breaks[i])}`
                  : `${fmt(breaks[i])} – ${fmt(breaks[i + 1])}`}
              </span>
            </li>
          ))}
          {hasNoData && (
            <li className="flex items-center gap-2 pt-1 mt-1 border-t border-white/10">
              <span className="inline-block w-4 h-3.5 rounded ring-1 ring-white/15" style={{ background: NO_DATA }} />
              <span className="text-white/70">sem dado / não residencial</span>
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
