"use client";

/**
 * Fundo do mapa, escolhido pelo usuário (claro / escuro / ruas / satélite) via
 * useMapLayout — a escolha fica no navegador e vale para todos os mapas.
 *
 * Este componente também DESENHA O SELETOR no canto do mapa. Como todo mapa do
 * sistema usa este fundo, todo mapa ganha o seletor — inclusive os que vierem
 * depois —, sem cada tela ter de lembrar de colocá-lo.
 *
 * Claro    -> Esri Light Gray Canvas — padrão
 * Escuro   -> Esri Dark Gray Canvas
 * Ruas     -> Esri World Street Map
 * Satélite -> Esri World Imagery
 *
 * POR QUE NÃO É MAIS CARTO (out/2026): o CartoDB passou a exigir chave de API
 * nos basemaps e os tiles viraram uma imagem de aviso — "API KEY REQUIRED"
 * carimbado por cima do mapa inteiro. Dava para confirmar sem abrir o
 * navegador: o CDN devolvia 200 com SEMPRE os mesmos 2.049 bytes, em qualquer
 * zoom e qualquer lugar do mundo, enquanto um tile de verdade muda de tamanho
 * conforme o conteúdo.
 *
 * Tudo vem do Esri, e não de OpenStreetMap, por três motivos: os cinzas são
 * desenhados como fundo para dado sobreposto (é o nosso caso — bolinhas de
 * votação por cima); todas as camadas saem do MESMO host, então a allowlist de
 * img-src do CSP é uma linha só; e o OSM público desaconselha uso comercial
 * pesado na política de tiles deles.
 *
 * `key` força o Leaflet a recriar o TileLayer ao trocar de camada.
 */
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import L from "leaflet";
import { TileLayer, useMap } from "react-leaflet";

import { useMapLayout } from "@/lib/useMapLayout";
import { MapLayoutSelector } from "./MapLayoutSelector";

const ATTRIB_ESRI =
  'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community';

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";

const URL_LIGHT = `${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`;
const URL_DARK = `${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`;
const URL_SAT = `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`;
// Conferido no centro do Rio: tile de verdade (tamanho variando) até o zoom 19.
const URL_RUAS = `${ESRI}/World_Street_Map/MapServer/tile/{z}/{y}/{x}`;

// Nos mapas Canvas do Esri os RÓTULOS são uma camada à parte — nomes de rua,
// bairro e município não vêm no fundo. Sem ela o mapa fica chapado perto do
// CartoDB Voyager, que trazia os nomes embutidos. Entram por cima do fundo e
// por baixo dos dados (ambos no tilePane), que é exatamente como o Voyager se
// comportava: as bolinhas de votação cobrem o rótulo, não o contrário.
const URL_LIGHT_LABELS = `${ESRI}/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`;
const URL_DARK_LABELS = `${ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`;

// Os cinzas do Esri só têm tile de verdade até o zoom 16 — do 17 em diante
// devolvem sempre o mesmo tile vazio. `maxNativeZoom` faz o Leaflet ampliar o
// último nível real em vez de mostrar mapa em branco: fica levemente borrado
// no zoom fundo, mas nunca vazio. Ruas e satélite não precisam, têm tile até 19.
const MAX_NATIVE_CINZA = 16;
// O satélite tem imagem até o zoom 19 nas metrópoles, mas no interior para no
// 17: acima disso o Esri devolve a placa "Map data not yet available" (200,
// sempre os mesmos 2.521 bytes — conferido em Xique-Xique, Oiapoque, Cruzeiro
// do Sul, Uruguaiana). Ampliar o 17 perde um pouco de nitidez na capital, mas
// nunca troca o mapa por uma placa cinza.
const MAX_NATIVE_SATELITE = 17;

type Props = {
  /** false esconde o seletor de camada (o fundo continua seguindo a escolha). */
  seletor?: boolean;
};

export function ThemedTileLayer({ seletor = true }: Props) {
  const [layout] = useMapLayout();
  return (
    <>
      <Fundo layout={layout} />
      {seletor && <SeletorNoMapa />}
    </>
  );
}

function Fundo({ layout }: { layout: ReturnType<typeof useMapLayout>[0] }) {
  if (layout === "satellite") {
    return (
      <TileLayer
        key="satellite"
        attribution={ATTRIB_ESRI}
        url={URL_SAT}
        maxZoom={19}
        maxNativeZoom={MAX_NATIVE_SATELITE}
      />
    );
  }
  if (layout === "streets") {
    return (
      <TileLayer key="streets" attribution={ATTRIB_ESRI} url={URL_RUAS} maxZoom={19} />
    );
  }

  const escuro = layout === "dark";
  return (
    <>
      <TileLayer
        key={layout}
        attribution={ATTRIB_ESRI}
        url={escuro ? URL_DARK : URL_LIGHT}
        maxZoom={19}
        maxNativeZoom={MAX_NATIVE_CINZA}
      />
      <TileLayer
        key={`${layout}-labels`}
        url={escuro ? URL_DARK_LABELS : URL_LIGHT_LABELS}
        maxZoom={19}
        maxNativeZoom={MAX_NATIVE_CINZA}
      />
    </>
  );
}

/**
 * O seletor, pendurado no canto inferior esquerdo do próprio mapa.
 *
 * Canto inferior esquerdo porque é o único livre em todos os mapas: o zoom
 * fica em cima à esquerda, a atribuição embaixo à direita, e várias telas já
 * usam o alto à direita para os controles delas.
 */
function SeletorNoMapa() {
  const map = useMap();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    // O seletor mora DENTRO do contêiner do mapa: sem isto, clicar num botão
    // também arrastaria o mapa, e rolar em cima dele daria zoom.
    L.DomEvent.disableClickPropagation(ref.current);
    L.DomEvent.disableScrollPropagation(ref.current);
  }, []);

  return createPortal(
    // z-[1000]: mesma altura dos controles do próprio Leaflet (zoom, atribuição).
    // No celular sobe um pouco: ali a atribuição do Esri não cabe numa linha,
    // vira duas de ponta a ponta no rodapé, e o seletor ficava por cima dela.
    <div ref={ref} className="absolute bottom-9 sm:bottom-3 left-3 z-[1000]">
      <MapLayoutSelector compacto />
    </div>,
    map.getContainer(),
  );
}
