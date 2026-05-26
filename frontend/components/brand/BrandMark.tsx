"use client";

/**
 * Marca MareNostrum (monograma "M" dourado oficial).
 *
 * Sem flicker: o SVG dourado fica ATRÁS como placeholder; o PNG oficial
 * (/logo-mark.png) sobrepõe e só aparece (fade-in) quando termina de carregar.
 * Se o PNG falhar, o SVG permanece — nunca mostra ícone quebrado.
 */
import { useState } from "react";

export function BrandMark({ className = "w-10 h-10" }: { className?: string }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  return (
    <span className={`relative inline-block ${className}`} aria-label="MareNostrum">
      {/* Placeholder/fallback SVG dourado (sempre presente atrás) */}
      <svg
        viewBox="0 0 100 116"
        xmlns="http://www.w3.org/2000/svg"
        className="absolute inset-0 w-full h-full"
        role="img"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="mn-gold" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#f3e4a8" />
            <stop offset="45%" stopColor="#d4af52" />
            <stop offset="100%" stopColor="#a9802f" />
          </linearGradient>
        </defs>
        <path
          fill="url(#mn-gold)"
          d="M2 4 h22 l26 40 26-40 h22 v108 h-22 V46 l-20 31 h-12 L24 46 v66 H2 Z"
        />
        <path fill="#1c1b1a" d="M74 60 l14 21 v-21 Z" />
      </svg>
      {!failed && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src="/logo-mark.png"
          alt="MareNostrum"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-200 ${
            loaded ? "opacity-100" : "opacity-0"
          }`}
        />
      )}
    </span>
  );
}
