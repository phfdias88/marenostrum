"use client";

/**
 * Popup de município compartilhado pelos mapas nacionais (partidário e virada).
 *
 * POR QUE POPUP, se já existe o tooltip: tooltip só aparece com o mouse em
 * cima. No celular não há "passar o mouse" — sem o popup, quem toca num ponto
 * não vê nada. O popup abre no clique/toque e ainda leva à página do município.
 *
 * Os marcadores são criados na mão (L.circleMarker, fora do React), então o
 * conteúdo é HTML em texto. O botão não pode ter um onClick do React: ele é
 * ligado quando o popup abre, e navega pelo roteador do Next para respeitar o
 * basePath (/sistema) — um <a href> cru sairia sem ele.
 */
import { useEffect } from "react";
import type L from "leaflet";
import { useRouter } from "next/navigation";

/** Nomes vêm do TSE e entram em HTML: escapar sempre. */
export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

export function botaoDoMunicipio(id: string): string {
  return (
    `<button type="button" data-municipio="${esc(id)}" ` +
    `style="margin-top:6px;padding:0;border:0;background:none;cursor:pointer;` +
    `font:inherit;font-weight:600;color:hsl(var(--primary))">` +
    `Abrir município →</button>`
  );
}

/** Liga o botão "Abrir município" de qualquer popup aberto neste mapa. */
export function useAbrirMunicipio(map: L.Map): void {
  const router = useRouter();
  useEffect(() => {
    const aoAbrir = (e: L.PopupEvent) => {
      const botao = e.popup
        .getElement()
        ?.querySelector<HTMLButtonElement>("[data-municipio]");
      if (!botao) return;
      botao.onclick = () =>
        router.push(`/dashboard/analises/municipio/${botao.dataset.municipio}`);
    };
    map.on("popupopen", aoAbrir);
    return () => {
      map.off("popupopen", aoAbrir);
    };
  }, [map, router]);
}
