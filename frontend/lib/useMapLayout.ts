"use client";

/**
 * Layout (camada de tiles) escolhido pelo usuário pros mapas: claro, escuro
 * ou satélite. Persistido em localStorage e compartilhado entre todas as
 * instâncias de mapa via um evento custom (mn-map-layout) — assim o seletor
 * e o ThemedTileLayer (componentes separados dentro do mesmo mapa) sincronizam.
 */
import { useEffect, useState } from "react";

export type MapLayout = "light" | "dark" | "satellite";

const KEY = "mn_map_layout";
const EVENT = "mn-map-layout";

function read(): MapLayout {
  if (typeof window === "undefined") return "light";
  const v = window.localStorage.getItem(KEY);
  return v === "dark" || v === "satellite" ? v : "light";
}

export function useMapLayout(): [MapLayout, (l: MapLayout) => void] {
  const [layout, setLayoutState] = useState<MapLayout>("light");

  // Lê do localStorage só no cliente (evita mismatch de hidratação).
  useEffect(() => {
    setLayoutState(read());
    const handler = () => setLayoutState(read());
    window.addEventListener(EVENT, handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener(EVENT, handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  function setLayout(l: MapLayout) {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(KEY, l);
      window.dispatchEvent(new Event(EVENT));
    }
    setLayoutState(l);
  }

  return [layout, setLayout];
}
