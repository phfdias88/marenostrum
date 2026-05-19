import { ImageResponse } from "next/og";

// Favicon gerado: "M" branco em quadrado com gradiente azul (marca MareNostrum)
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#1c1b1a",
          color: "#d4af52",
          fontSize: 24,
          fontWeight: 800,
          borderRadius: 7,
          border: "1.5px solid #d4af52",
        }}
      >
        M
      </div>
    ),
    { ...size },
  );
}
