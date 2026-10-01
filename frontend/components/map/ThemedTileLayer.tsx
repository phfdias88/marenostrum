"use client";

/**
 * TileLayer com camada escolhida pelo usuário (claro / escuro / satélite),
 * via useMapLayout (localStorage, compartilhado entre os mapas).
 *
 * Claro    -> Esri Light Gray Canvas — padrão
 * Escuro   -> Esri Dark Gray Canvas
 * Satélite -> Esri World Imagery
 *
 * POR QUE NÃO É MAIS CARTO (out/2026): o CartoDB passou a exigir chave de API
 * nos basemaps e os tiles viraram uma imagem de aviso — "API KEY REQUIRED"
 * carimbado por cima do mapa inteiro. Dava para confirmar sem abrir o
 * navegador: o CDN devolvia 200 com SEMPRE os mesmos 2.049 bytes, em qualquer
 * zoom e qualquer lugar do mundo, enquanto um tile de verdade muda de tamanho
 * conforme o conteúdo.
 *
 * Trocamos pelos cinzas do Esri, e não por OpenStreetMap ou Street Map, por
 * três motivos: são desenhados como fundo para dado sobreposto (é o nosso caso
 * — bolinhas de votação por cima); vêm do MESMO host que o satélite já usava,
 * então a allowlist de img-src do CSP não precisou mudar; e o OSM público
 * desaconselha uso comercial pesado na política de tiles deles.
 *
 * `key={layout}` força o Leaflet a recriar o TileLayer ao trocar de camada.
 */
import { TileLayer } from "react-leaflet";

import { useMapLayout } from "@/lib/useMapLayout";

const ATTRIB_ESRI =
  'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community';

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";

const URL_LIGHT = `${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`;
const URL_DARK = `${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`;
const URL_SAT = `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`;

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
// no zoom fundo, mas nunca vazio. O satélite não precisa disso, tem tile até 19.
const MAX_NATIVE_CINZA = 16;

export function ThemedTileLayer() {
  const [layout] = useMapLayout();

  if (layout === "satellite") {
    return (
      <TileLayer
        key="satellite"
        attribution={ATTRIB_ESRI}
        url={URL_SAT}
        maxZoom={19}
      />
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
