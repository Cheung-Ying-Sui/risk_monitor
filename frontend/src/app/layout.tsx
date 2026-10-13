import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import { AuthGate } from "@/components/auth-gate";
import "./globals.css";
import "./typography.css";
import "./theme.css";

const ibmPlexSans = IBM_Plex_Sans({
  variable: "--font-ibm-plex-sans",
  subsets: ["latin"],
  weight: "variable",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
  adjustFontFallback: true,
});

export const metadata: Metadata = {
  title: "中化保险经纪海事智能平台",
  description: "海事运营、船舶跟踪与风险情报平台。",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="zh-CN"
      data-theme="light"
      className={`${ibmPlexSans.variable} h-full antialiased`}
    >
      <body><AuthGate>{children}</AuthGate></body>
    </html>
  );
}
