import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const size = {
  width: 64,
  height: 64,
};

export const contentType = "image/png";

export default async function Icon() {
  const sinochemLogo = await readFile(join(process.cwd(), "public/branding/sinochem-capital-logo.png"));
  const sinochemLogoDataUrl = `data:image/png;base64,${sinochemLogo.toString("base64")}`;

  return new ImageResponse(
    (
      <div
        style={{
          position: "relative",
          width: "64px",
          height: "64px",
          display: "flex",
          overflow: "hidden",
          background: "transparent",
        }}
      >
        {/* Render the original wide logo at a fixed height and clip after its left-hand symbol. */}
        <img
          src={sinochemLogoDataUrl}
          width={220}
          height={44}
          alt=""
          style={{ position: "absolute", top: "10px", left: "3px" }}
        />
      </div>
    ),
    size,
  );
}
