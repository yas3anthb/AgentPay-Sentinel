import type { Metadata } from "next";
import localFont from "next/font/local";

import { Header } from "@/components/shell/header";

import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "AgentPay Sentinel",
  description:
    "A pre-payment security gateway for autonomous agents — not a fraud dashboard.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${geistSans.variable} ${geistMono.variable} min-h-screen`}>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-ink-raised focus:px-3 focus:py-2 focus:font-mono focus:text-xs focus:text-signal-idle"
        >
          Skip to content
        </a>
        <Header />
        <main id="main" className="mx-auto max-w-[1600px] px-5 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
