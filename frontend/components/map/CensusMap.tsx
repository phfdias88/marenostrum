"use client";

/**
 * Mapa coroplético de setores/municípios (IBGE Censo 2022).
 * Renderiza GeoJSON colorido por um indicador, com legenda, tooltip no hover
 * e destaque do selecionado. Client-only (Leaflet usa window) — importar via
 * next/dynamic({ssr:false}).
 */
import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import L from "leaflet";
import { GeoJSON, MapContainer, Pane, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { ThemedTileLayer } from "./ThemedTileLayer";

import {
  type CensusIndicator,
  INDICATOR_FMT as FMT,
  INDICATOR_LABEL as LABEL,
} from "@/lib/census-indicators";

// Re-export pra quem ainda importa o tipo daqui (ex.: página do censo).
export type { CensusIndicator };

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
const RAMP = ["#ffd98a", "#f9b64d", "#f0902f", "#df6a2b", "#c53f2a", "#8f1d2c"];
const NO_DATA = "#9aa0a6";

const numFmt = new Intl.NumberFormat("pt-BR");
// FMT e LABEL agora vêm de @/lib/census-indicators (sem Leaflet, reusável na página).

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

// Bounds a partir das coordenadas cruas do FeatureCollection — SEM instanciar
// um segundo L.geoJSON só pra getBounds() (aquilo duplicava o parse dos ~13k
// setores e comia o orçamento do render de mosaico). Varre os arrays de coords
// sem alocar L.LatLng por vértice.
function boundsFromFC(fc: FC): L.LatLngBounds | null {
  let minLat = Infinity, minLng = Infinity, maxLat = -Infinity, maxLng = -Infinity;
  const scan = (c: unknown): void => {
    if (!Array.isArray(c)) return;
    if (typeof c[0] === "number" && typeof c[1] === "number") {
      const lng = c[0] as number, lat = c[1] as number;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lng < minLng) minLng = lng;
      if (lng > maxLng) maxLng = lng;
      return;
    }
    for (const x of c) scan(x);
  };
  for (const f of fc.features) {
    scan((f.geometry as { coordinates?: unknown } | null)?.coordinates);
  }
  if (minLat === Infinity) return null;
  return L.latLngBounds([minLat, minLng], [maxLat, maxLng]);
}

function FitBounds({ data }: { data: FC }) {
  const map = useMap();
  useEffect(() => {
    if (!data.features.length) return;
    const b = boundsFromFC(data);
    // animate:false — senão o fit é engolido na init do mapa (gotcha do projeto).
    if (b && b.isValid()) map.fitBounds(b, { padding: [16, 16], animate: false });
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
      lyr.setStyle({ weight: 1.6, color: "#ffe6a3", fillOpacity: 0.92 });
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
  bairroContours,
  distritoContours,
}: {
  data: FC;
  indicator: CensusIndicator;
  onSelect: (props: Record<string, number | string | null>) => void;
  focusIds?: string[] | null;
  // Muda quando a MALHA muda (setor/distrito/bairro) com os MESMOS setores —
  // força recriar o layer (senão a repintura in-place lê as props antigas).
  dataVersion?: string;
  // Contornos (setores dissolvidos) sobrepostos nas panes mn-bairros/mn-distritos.
  bairroContours?: FC | null;
  distritoContours?: FC | null;
}) {
  const breaks = useMemo(
    () => computeBreaks(data.features.map((f) => f.properties[indicator] as number)),
    [data, indicator],
  );
  const selectedRef = useRef<L.Path | null>(null);
  const layerReg = useRef<Map<string, L.Path>>(new Map());
  const geoRef = useRef<L.GeoJSON | null>(null);
  const fmt = FMT[indicator];
  // Legenda no mobile: compacta (barra de gradiente) por padrão; o toque
  // expande a lista completa de faixas. No desktop a lista fica sempre aberta.
  const [legendOpen, setLegendOpen] = useState(false);
  // key NÃO inclui o indicador: trocar de indicador repinta os polígonos
  // in-place (setStyle) em vez de recriar o layer inteiro (caro no Rio).
  const key = `${String(data.features[0]?.properties?.cd_setor ?? data.features[0]?.properties?.cd_mun ?? "")}-${data.features.length}-${dataVersion ?? ""}`;

  const baseStyle = (v: number | null) => ({
    fillColor: colorFor(v, breaks),
    weight: 0.6,
    color: "#7a5b1e",
    // Semi-transparente: deixa o mapa-base (ruas/rótulos) aparecer sob o
    // choropleth e não "esconde" o que estiver embaixo. O realce de
    // hover/clique sobe pra ~0.92 pra manter o contraste na interação.
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
      // Distrito no tooltip da CAMADA BASE (malha dissolvida por bairro): os
      // contornos viraram decoração (pointer-events none) e este é o único
      // lugar onde o distrito consegue aparecer no hover.
      (p.nm_dist
        ? `<div style="opacity:.75;font-size:10px;margin-bottom:2px">Distrito: ${p.nm_dist}</div>`
        : "") +
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
        {/* Panes ordenados (zIndex) — força a ordem das camadas por cima do
            tilePane (200). Hoje só a malha de setores existe; as bandas 420/430
            ficam RESERVADAS para, quando houver, sobrepor contornos de bairro e
            distrito (fillOpacity 0, bordas grossas) sem que os setores os
            escondam. É a infraestrutura de MapPanes pedida. */}
        <Pane name="mn-setores" style={{ zIndex: 410 }} />
        {/* pointerEvents:none nas panes de CONTORNO: elas ficam ACIMA da
            camada clicável e, com preferCanvas, o canvas da pane superior
            intercepta o clique — inclusive VAZIO (depois de desligar o toggle
            de contornos o canvas órfão continuava engolindo cliques e o
            usuário não conseguia mais selecionar bairro). Contorno é
            decoração: o clique deve SEMPRE cair na camada base. */}
        <Pane name="mn-bairros" style={{ zIndex: 420, pointerEvents: "none" }} />
        <Pane name="mn-distritos" style={{ zIndex: 430, pointerEvents: "none" }} />
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
          pane="mn-setores"
          data={data as unknown as GeoJSON.GeoJsonObject}
          style={(feature) => baseStyle((feature?.properties?.[indicator] ?? null) as number | null)}
          onEachFeature={(feature, layer) => {
            const p = feature.properties as Record<string, number | string | null>;
            const path = layer as L.Path;
            // Registra por cd_setor (modo setor) OU por nome (modo dissolvido:
            // 1 polígono por bairro/distrito, sem cd_setor) — assim o
            // FocusController acha a camada e o mapa VOA até o bairro na busca.
            const regKey = String(p.cd_setor ?? p.nome ?? p.cd_mun ?? "");
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
                path.setStyle({ weight: 2.8, color: "#ffe6a3", fillOpacity: 0.95 });
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
                if (path !== selectedRef.current) {
                  path.setStyle({ weight: 1.8, color: "#fdf3dd", fillOpacity: 0.92 });
                  path.bringToFront();
                }
              },
              mouseout: () => {
                if (path !== selectedRef.current) path.setStyle(baseStyleRef.current(curV()));
              },
            });
          }}
        />

        {/* Contorno de BAIRROS (setores dissolvidos) — pane mn-bairros (zIndex
            420), acima dos setores; sem preenchimento, borda destacada.
            interactive={false}: contorno NUNCA captura clique/hover (o clique
            pertence à camada base, que já mostra o nome no tooltip). Sem isso,
            o fill transparente interceptava o clique do bairro. */}
        {bairroContours && bairroContours.features.length > 0 && (
          <GeoJSON
            key={`bairro-${bairroContours.features.length}-${String(bairroContours.features[0]?.properties?.nome ?? "")}`}
            data={bairroContours as unknown as GeoJSON.GeoJsonObject}
            pane="mn-bairros"
            interactive={false}
            style={{ fillOpacity: 0, weight: 1.6, color: "#8fcddb", opacity: 0.85, interactive: false }}
          />
        )}

        {/* Contorno de DISTRITOS — pane mn-distritos (zIndex 430), no topo;
            borda mais grossa e tracejada. Também interactive={false}. */}
        {distritoContours && distritoContours.features.length > 0 && (
          <GeoJSON
            key={`distrito-${distritoContours.features.length}-${String(distritoContours.features[0]?.properties?.nome ?? "")}`}
            data={distritoContours as unknown as GeoJSON.GeoJsonObject}
            pane="mn-distritos"
            interactive={false}
            style={{ fillOpacity: 0, weight: 3, color: "#3f9cb5", opacity: 0.95, dashArray: "6 3", interactive: false }}
          />
        )}
      </MapContainer>

      {/* Legenda — tokens do tema (bg-card/border/foreground) pra funcionar no
          claro E no escuro; antes era bg-black/75 com texto branco fixo, que
          destoava no tema claro. */}
      <div className="absolute bottom-3 right-3 z-[400] rounded-xl bg-card/85 backdrop-blur-md px-3.5 py-2.5 border border-border shadow-xl shadow-black/20 text-[11px] text-foreground">
        {(() => {
          const legendList = (
            <ul className="space-y-1">
              {RAMP.map((c, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span
                    className="inline-block w-4 h-3.5 rounded ring-1 ring-border"
                    style={{ background: c, boxShadow: `0 0 6px ${c}55` }}
                  />
                  <span className="tabular-nums text-foreground/85">
                    {i === RAMP.length - 1
                      ? `≥ ${fmt(breaks[i])}`
                      : `${fmt(breaks[i])} – ${fmt(breaks[i + 1])}`}
                  </span>
                </li>
              ))}
              {hasNoData && (
                <li className="flex items-center gap-2 pt-1 mt-1 border-t border-border">
                  <span className="inline-block w-4 h-3.5 rounded ring-1 ring-border" style={{ background: NO_DATA }} />
                  <span className="text-muted-foreground">sem dado / não residencial</span>
                </li>
              )}
            </ul>
          );
          return (
            <>
              {/* Mobile (< sm): versão compacta — barra única com o gradiente
                  do RAMP e min/max nas pontas; o toque expande a lista. */}
              <div className="sm:hidden">
                <button
                  type="button"
                  onClick={() => setLegendOpen((o) => !o)}
                  aria-expanded={legendOpen}
                  aria-label={legendOpen ? "Recolher a legenda de cores" : "Expandir a legenda de cores"}
                  className="block w-44 min-h-[40px] text-left"
                >
                  <span className="font-semibold tracking-wide block truncate">{LABEL[indicator]}</span>
                  <span
                    className="block h-2 rounded mt-1.5"
                    style={{ background: `linear-gradient(to right, ${RAMP.join(", ")})` }}
                  />
                  <span className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground tabular-nums">
                    <span>{fmt(breaks[0])}</span>
                    <span>≥ {fmt(breaks[RAMP.length - 1])}</span>
                  </span>
                </button>
                {legendOpen && <div className="mt-2">{legendList}</div>}
              </div>
              {/* Desktop (≥ sm): lista completa, sempre visível. */}
              <div className="hidden sm:block">
                <p className="font-semibold mb-2 tracking-wide">{LABEL[indicator]}</p>
                {legendList}
              </div>
            </>
          );
        })()}
      </div>
    </div>
  );
}
