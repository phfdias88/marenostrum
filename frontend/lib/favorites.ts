"use client";

/**
 * Favoritos do usuario — persistidos em localStorage (sem backend).
 * Guarda o minimo pra renderizar + linkar de volta.
 */
import { useCallback, useEffect, useState } from "react";

export type FavoriteKind = "candidate" | "municipality" | "party";

export type Favorite = {
  kind: FavoriteKind;
  id: string;
  label: string; // nome principal
  sub?: string; // subtitulo (partido/cargo ou UF)
  partyNumber?: number;
  state?: string;
};

const KEY = "mn_favorites_v1";

function read(): Favorite[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function write(items: Favorite[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
  // notifica outras instancias do hook na mesma aba
  window.dispatchEvent(new Event("mn-favorites"));
}

export function useFavorites() {
  const [items, setItems] = useState<Favorite[]>([]);

  useEffect(() => {
    setItems(read());
    const sync = () => setItems(read());
    window.addEventListener("mn-favorites", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("mn-favorites", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const isFav = useCallback(
    (kind: FavoriteKind, id: string) =>
      items.some((f) => f.kind === kind && f.id === id),
    [items],
  );

  const toggle = useCallback((fav: Favorite) => {
    const cur = read();
    const exists = cur.some((f) => f.kind === fav.kind && f.id === fav.id);
    const next = exists
      ? cur.filter((f) => !(f.kind === fav.kind && f.id === fav.id))
      : [fav, ...cur].slice(0, 100);
    write(next);
  }, []);

  return { items, isFav, toggle };
}
