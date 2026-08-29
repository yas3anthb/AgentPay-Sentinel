import type { Metadata } from "next";
import { Inter } from "next/font/google";
import localFont from "next/font/local";

import { Header } from "@/components/shell/header";

import "./globals.css";

/** UI type: everything the reader reads as language. */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

/** Data type: hashes, ids, policy versions, raw JSON. Nothing else. */
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
    <html lang="en" className={`${inter.variable} ${geistMono.variable}`}>
      <body className="min-h-screen font-sans text-body">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2 focus:text-caption focus:shadow-raised"
        >
          Skip to content
        </a>
        <Header />
        <main id="main" className="mx-auto max-w-[1560px] px-6 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
