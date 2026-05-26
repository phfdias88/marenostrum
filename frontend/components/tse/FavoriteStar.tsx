"use client";

import { Star } from "lucide-react";

import { useFavorites, type Favorite } from "@/lib/favorites";

export function FavoriteStar({
  fav,
  size = 18,
}: {
  fav: Favorite;
  size?: number;
}) {
  const { isFav, toggle } = useFavorites();
  const active = isFav(fav.kind, fav.id);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        toggle(fav);
      }}
      title={active ? "Remover dos favoritos" : "Adicionar aos favoritos"}
      className={`shrink-0 transition-colors ${
        active ? "text-amber-400" : "text-muted-foreground hover:text-amber-400"
      }`}
    >
      <Star className="" width={size} height={size} fill={active ? "currentColor" : "none"} />
    </button>
  );
}
