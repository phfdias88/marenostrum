"use client";

/**
 * CandidateNeighborhoodMap — bolhas por bairro pra um candidato.
 *
 * Diferente do CandidateVoteMap (que mostra por municipio), aqui usa
 * o endpoint /candidates/{id}/by-neighborhood com filtro por municipio.
 * Cada bolha = centroide do bairro, raio = sqrt(votos/max) * 35.
 */
import { AlertTriangle, Landmark, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Pane,
  Popup,
  Tooltip,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
// Clustering dos locais de votação (milhares de pinos sem travar o mobile).
// Só o CSS base do plugin — os ícones de cluster são custom (.mn-cluster).
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";

import type { TseCandidateByNeighborhoodResponse } from "@/lib/types";
import { ThemedTileLayer } from "./ThemedTileLayer";

const numberFmt = new Intl.NumberFormat("pt-BR");
// "12,3 mil" nos ícones de cluster — número cheio fica no title/tooltip.
const compactFmt = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const DEFAULT_CENTER: [number, number] = [-14.5, -52.0];

// Faixa de cor pela FATIA do total de votos da camada (mesma semântica da
// legenda de bolhas: poucos → top). Share, não valor absoluto: funciona
// igual pra vereador (dezenas de votos) e deputado (milhares).
function voteBand(share: number): "emerald" | "amber" | "orange" | "red" {
  return share >= 0.35
    ? "red"
    : share >= 0.15
      ? "orange"
      : share >= 0.05
        ? "amber"
        : "emerald";
}

function fmtVotes(v: number): string {
  return v >= 1000 ? compactFmt.format(v) : numberFmt.format(v);
}

export type VotingPlacePoint = {
  id: string;
  name: string;
  neighborhood: string | null;
  lat: number;
  lng: number;
  electors: number | null;
  /** Município do local — desambigua escolas homônimas ("Nome (Município)"). */
  municipality?: string | null;
  /** Endereço (novo endpoint /voting-locations). */
  address?: string | null;
  /** Votos do candidato NESTE local (só na consulta por candidato). */
  votes?: number | null;
};

// Rótulo composto "Bairro (Município)" — regra de exibição do PO: deputado
// recebe voto no estado inteiro e todo município tem um "Centro"; sem o
// município junto, bairros homônimos viram ruído.
function nbLabel(r: { neighborhood: string; municipality_name?: string | null }): string {
  return r.municipality_name
    ? `${r.neighborhood} (${r.municipality_name})`
    : r.neighborhood;
}

/** Ponto pra onde o mapa deve VOAR (clique numa barra do gráfico). O `n` é um
 *  nonce: clicar de novo na MESMA barra re-dispara o voo. */
export type MapFocus = { lat: number; lng: number; zoom: number; n: number };

/** Toggle da camada de locais na barra de controle DO MAPA. O ESTADO vive na
 *  página (separação de responsabilidades); aqui só a UI do botão. */
export type PlacesControl = {
  active: boolean;
  disabled: boolean;
  loading?: boolean;
  /** Fetch dos locais falhou — o botão mostra o alerta (religar tenta de novo). */
  error?: boolean;
  onToggle: () => void;
};

export default function CandidateNeighborhoodMap({
  data,
  votingPlaces,
  placesTotal,
  placesControl,
  focus,
}: {
  data: TseCandidateByNeighborhoodResponse;
  /** Camada opcional de locais de votação (marcadores discretos). */
  votingPlaces?: VotingPlacePoint[];
  /** Total REAL de locais no servidor (quando o cap de 5000 cortou a lista). */
  placesTotal?: number | null;
  /** Botão "Locais de votação" na barra de controle do mapa (opcional). */
  placesControl?: PlacesControl;
  /** Voa até o ponto (sincronia gráfico → mapa). */
  focus?: MapFocus | null;
}) {
  const withCoords = useMemo(
    () => data.items.filter((i) => i.avg_lat != null && i.avg_lng != null),
    [data.items],
  );
  const missing = data.items.length - withCoords.length;
  const maxVotes = withCoords[0]?.votes ?? 1;

  return (
    <div className="h-full w-full flex flex-col">
      <div className="flex-1 relative">
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={4}
          scrollWheelZoom
          preferCanvas
          className="h-full w-full"
        >
          <ThemedTileLayer />

          {/* Pane DEDICADA pros locais de votação, ACIMA do overlayPane (400)
              onde vivem as bolhas de bairro: garante que os pontos azuis
              nunca fiquem escondidos SOB uma bolha grande — z-index explícito
              em vez de depender da ordem de montagem das camadas canvas. */}
          <Pane name="mn-places" style={{ zIndex: 640 }} />

          {withCoords.map((r) => {
            const pct = r.votes / maxVotes;
            const radius = Math.max(8, Math.sqrt(pct) * 35);
            const color =
              pct > 0.7
                ? "#dc2626"
                : pct > 0.4
                  ? "#f97316"
                  : pct > 0.15
                    ? "#f0ad4e"
                    : "#5cb85c";
            return (
              <CircleMarker
                // Chave COMPOSTA: só o bairro colidia em homônimos estaduais
                // (todo "Centro" do estado = mesma key React).
                key={`${r.municipality_id ?? ""}-${r.neighborhood}`}
                center={[r.avg_lat as number, r.avg_lng as number]}
                radius={radius}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.55,
                  weight: 1.5,
                }}
              >
                <Tooltip direction="top" offset={[0, -4]} className="mn-tip" opacity={1}>
                  <span>
                    {nbLabel(r)} · <b>{numberFmt.format(r.votes)}</b>
                  </span>
                </Tooltip>
                <Popup>
                  <div className="text-sm">
                    <p className="font-semibold">{nbLabel(r)}</p>
                    <p className="text-primary font-bold text-base">
                      {numberFmt.format(r.votes)} votos
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {numberFmt.format(r.places_count)} local(is)
                      {r.electors_total > 0 && (
                        <>
                          {" · "}
                          {numberFmt.format(r.electors_total)} eleitores
                        </>
                      )}
                    </p>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}

          {/* Camada de locais de votação (marcadores pequenos, azuis) —
              IMPERATIVA: até 3000 locais viravam ~9000 mounts React
              (CircleMarker+Tooltip+Popup) e o rebuild por tecla do filtro
              pesava no mobile. 1 L.layerGroup em canvas resolve. */}
          {votingPlaces && votingPlaces.length > 0 && (
            <PlacesLayer places={votingPlaces} />
          )}

          <AutoFit
            points={withCoords.map(
              (r) => [r.avg_lat as number, r.avg_lng as number] as [number, number],
            )}
          />
          <FlyTo focus={focus} />
        </MapContainer>

        {/* Barra de controle do mapa (top-right, mesmo padrão do toggle
            Bolhas/Heatmap do mapa de municípios). Só a UI: o estado da camada
            vive na página, desacoplado dos filtros de bairro. */}
        {placesControl && (
          <div className="absolute top-3 right-3 z-[400] flex bg-card/80 backdrop-blur border border-border rounded-lg p-1 text-xs">
            <button
              onClick={placesControl.onToggle}
              disabled={placesControl.disabled}
              title={
                placesControl.disabled
                  ? "Disponível na visão por bairro"
                  : placesControl.error
                    ? "Falha ao carregar os locais. Desligue e ligue para tentar de novo."
                    : placesControl.active
                      ? "Ocultar locais de votação"
                      : "Mostrar os locais de votação (agrupados por proximidade)"
              }
              className={
                // Desligado NÃO é cinza-fantasma: chip com borda e texto vivos,
                // rótulo vira verbo ("Exibir…") — senão o usuário não percebe
                // que é um botão e acha que a feature "não aparece" (aconteceu).
                "px-3 py-1.5 rounded-md inline-flex items-center gap-1.5 border transition-colors disabled:opacity-45 disabled:cursor-not-allowed " +
                (placesControl.active
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-foreground border-border hover:border-primary/60")
              }
            >
              {placesControl.loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : placesControl.error ? (
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              ) : (
                <Landmark className="w-3.5 h-3.5" />
              )}{" "}
              {placesControl.active ? "Locais de votação" : "Exibir locais de votação"}
            </button>
          </div>
        )}
      </div>

      <div className="px-3 py-2 text-xs text-muted-foreground bg-card border-t border-border flex items-center justify-between gap-2 flex-wrap">
        <span>
          {numberFmt.format(withCoords.length)} bairro(s) plotado(s)
          {missing > 0 && (
            <span className="ml-2 text-amber-500">
              · {numberFmt.format(missing)} sem coordenadas
            </span>
          )}
          {votingPlaces && votingPlaces.length > 0 && (
            <span className="ml-2 inline-flex items-center gap-1 text-blue-500">
              · <span className="w-2 h-2 rounded-full bg-blue-500" />
              {placesTotal != null && placesTotal > votingPlaces.length
                ? `${numberFmt.format(votingPlaces.length)} de ${numberFmt.format(placesTotal)} locais (maiores votações)`
                : `${numberFmt.format(votingPlaces.length)} locais de votação`}
            </span>
          )}
        </span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-emerald-500" /> poucos
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-amber-500" /> médios
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-orange-500" /> muitos
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-red-600" /> top
          </span>
        </span>
      </div>
    </div>
  );
}

/** Visão LOCAIS do modal: mapa SÓ de locais de votação clusterizados (sem
 *  bolhas de bairro), com rodapé de contagem. Reusa PlacesLayer/AutoFit/FlyTo. */
export function VotingPlacesMap({
  places,
  total,
  focus,
}: {
  places: VotingPlacePoint[];
  /** Total real no servidor (cap de 5000 → "X de Y"). */
  total?: number | null;
  focus?: MapFocus | null;
}) {
  const pts = useMemo(
    () => places.map((p) => [p.lat, p.lng] as [number, number]),
    [places],
  );
  return (
    <div className="h-full w-full flex flex-col">
      <div className="flex-1 relative">
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={4}
          scrollWheelZoom
          preferCanvas
          className="h-full w-full"
        >
          <ThemedTileLayer />
          <Pane name="mn-places" style={{ zIndex: 640 }} />
          {places.length > 0 && <PlacesLayer places={places} />}
          <AutoFit points={pts} />
          <FlyTo focus={focus} />
        </MapContainer>
      </div>
      <div className="px-3 py-2 text-xs text-muted-foreground bg-card border-t border-border flex items-center justify-between gap-2 flex-wrap">
        <span>
          {total != null && total > places.length
            ? `${numberFmt.format(places.length)} de ${numberFmt.format(total)} locais (maiores votações)`
            : `${numberFmt.format(places.length)} ${places.length === 1 ? "local de votação" : "locais de votação"}`}
          <span className="ml-1">
            · o número no grupo é a SOMA de votos da área
          </span>
        </span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-emerald-500" /> poucos
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-amber-500" /> médios
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-orange-500" /> muitos
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-red-600" /> reduto
          </span>
        </span>
      </div>
    </div>
  );
}

function AutoFit({ points }: { points: [number, number][] }) {
  const map = useMap();
  // Assinatura por VALOR: os filtros do modal re-renderizam o mapa com um
  // array NOVO (mesma coordenada) a cada tecla/fetch — refit por identidade
  // resetava o pan/zoom do usuário toda hora. Só refita quando o CONJUNTO
  // de pontos muda de fato.
  const sig = points.map((p) => p.join(",")).join("|");
  const ptsRef = useRef(points);
  ptsRef.current = points;
  useEffect(() => {
    const pts = ptsRef.current;
    if (pts.length === 0) return;
    if (pts.length === 1) {
      map.setView(pts[0], 14, { animate: false });
      return;
    }
    const bounds = L.latLngBounds(pts);
    // animate:false — senão o enquadramento é engolido na init do mapa (gotcha).
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14, animate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, map]);
  return null;
}

// Voa até o ponto clicado no gráfico. AQUI pode animar: o gotcha do
// animate:false vale só pra chamadas na INIT do mapa (engolidas) — clique do
// usuário chega com o mapa vivo, e o voo dá o feedback visual pedido pelo PO.
function FlyTo({ focus }: { focus?: MapFocus | null }) {
  const map = useMap();
  useEffect(() => {
    if (!focus) return;
    map.setView([focus.lat, focus.lng], focus.zoom, { animate: true });
  }, [focus, map]);
  return null;
}

// Escapa HTML pra bindTooltip/bindPopup (strings cruas do TSE).
function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Locais como UMA camada imperativa (mesmo padrão do BubblesLayer do
// CandidateVoteMap): sem mount React por marcador. Com CLUSTERING
// (leaflet.markercluster): um deputado estadual tem MILHARES de locais com
// voto — plotar tudo solto travava o mobile; agrupado, o Leaflet só
// renderiza o que está no viewport/zoom. chunkedLoading fatia a inserção
// em frames (não bloqueia o main thread na carga).
function PlacesLayer({ places }: { places: VotingPlacePoint[] }) {
  const map = useMap();
  useEffect(() => {
    if (places.length === 0) return;
    // Total da camada: os clusters mostram a SOMA DE VOTOS da área (pedido do
    // PO — o candidato quer força eleitoral, não contagem de escolas) e a cor
    // segue a FATIA desse total. Camada sem votos (página de Bairros, fallback
    // geográfico 2024) mantém a contagem de locais em azul.
    const totalVotes = places.reduce((s, p) => s + (p.votes ?? 0), 0);
    const hasVotes = totalVotes > 0;
    const group = L.markerClusterGroup({
      chunkedLoading: true,
      maxClusterRadius: 60,
      // No zoom de rua o usuário quer VER as escolas, não bolhas agregadas.
      disableClusteringAtZoom: 16,
      spiderfyOnMaxZoom: true,
      showCoverageOnHover: false,
      iconCreateFunction: (cluster) => {
        const n = cluster.getChildCount();
        if (!hasVotes) {
          const size = n >= 100 ? "lg" : n >= 25 ? "md" : "sm";
          return L.divIcon({
            html: `<span>${n >= 1000 ? `${Math.round(n / 1000)}k` : n}</span>`,
            className: `mn-cluster mn-cluster-${size}`,
            iconSize: L.point(0, 0), // o tamanho real vem do CSS
          });
        }
        // Soma dos votos dos filhos (null/undefined contam 0).
        const sum = cluster
          .getAllChildMarkers()
          .reduce(
            (s, m) => s + ((m.options as { mnVotes?: number }).mnVotes ?? 0),
            0,
          );
        const share = sum / totalVotes;
        const band = voteBand(share);
        const size = share >= 0.15 ? "lg" : share >= 0.05 ? "md" : "sm";
        return L.divIcon({
          html: `<span title="${numberFmt.format(sum)} votos em ${n} ${n === 1 ? "local" : "locais"}">${fmtVotes(sum)}</span>`,
          className: `mn-cluster mn-cluster-${size} mn-cluster-${band}`,
          iconSize: L.point(0, 0),
        });
      },
    });
    for (const vp of places) {
      // Coordenada precisa ser um número VÁLIDO — lat/lng null/NaN derrubam
      // o marcador e a camada inteira "não aparece". (O backend já saneia;
      // isto é o cinto de segurança pra fontes antigas.)
      if (!Number.isFinite(vp.lat) || !Number.isFinite(vp.lng)) continue;
      const v = vp.votes ?? 0;
      // Com votos: pílula rotulada com os votos DAQUELA escola (requisito do
      // PO pro zoom final), na cor da fatia. Sem votos: ponto azul discreto.
      const m = hasVotes
        ? L.marker([vp.lat, vp.lng], {
            pane: "mn-places",
            icon: L.divIcon({
              html: `<span>${fmtVotes(v)}</span>`,
              className: `mn-pin mn-pin-${voteBand(totalVotes > 0 ? v / totalVotes : 0)}`,
              iconSize: L.point(0, 0),
            }),
            ...({ mnVotes: v } as object),
          })
        : L.circleMarker([vp.lat, vp.lng], {
            pane: "mn-places",
            radius: 4,
            color: "#1d4ed8",
            fillColor: "#3b82f6",
            fillOpacity: 0.9,
            weight: 1,
          });
      const muni = vp.municipality ? ` (${esc(vp.municipality)})` : "";
      const nb = vp.neighborhood ? ` · ${esc(vp.neighborhood)}` : "";
      const votos =
        vp.votes != null ? ` · ${numberFmt.format(vp.votes)} votos` : "";
      m.bindTooltip(`${esc(vp.name)}${muni}${nb}${votos}`, {
        direction: "top",
        offset: [0, -4],
        className: "mn-tip",
        opacity: 1,
      });
      m.bindPopup(
        `<div class="text-sm"><p class="font-semibold">${esc(vp.name)}${muni}</p>` +
          (vp.votes != null
            ? `<p class="mn-popup-votes">${numberFmt.format(vp.votes)} votos do candidato aqui</p>`
            : "") +
          (vp.neighborhood
            ? `<p class="text-xs text-muted-foreground">${esc(vp.neighborhood)}</p>`
            : "") +
          (vp.address
            ? `<p class="text-xs text-muted-foreground">${esc(vp.address)}</p>`
            : "") +
          (vp.electors != null && vp.electors > 0
            ? `<p class="text-xs text-muted-foreground">${numberFmt.format(vp.electors)} eleitores aptos</p>`
            : "") +
          "</div>",
      );
      group.addLayer(m);
    }
    group.addTo(map);
    return () => {
      map.removeLayer(group);
    };
  }, [places, map]);
  return null;
}
