import type { Config } from "tailwindcss";

/**
 * A committed palette, not a default one.
 *
 * The product is a security instrument, so the visual language is closer to an
 * oscilloscope than a SaaS dashboard: a near-black ground, hairline rules, and
 * exactly four semantic signal colours that mean the same thing everywhere —
 * in the tables, in the charts, and in the 3D scene.
 */
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#05070A", // page ground
          raised: "#0B1017", // panels
          sunken: "#030508",
        },
        hairline: {
          DEFAULT: "#17212C",
          bright: "#243343",
        },
        chalk: {
          DEFAULT: "#DCE5EE",
          muted: "#8496A8",
          faint: "#4F6072",
        },
        // The four signals. Nothing else in the app is allowed to use them.
        signal: {
          idle: "#4EC9C0", // teal — the system at rest
          allow: "#3FBF7F",
          approval: "#E0A340",
          block: "#F2637A",
          simulated: "#9B8CF5", // violet — scripted, never live
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgb(78 201 192 / 0.18), 0 0 32px -12px rgb(78 201 192 / 0.35)",
        panel: "0 1px 0 0 rgb(255 255 255 / 0.03) inset",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { opacity: "0.9", transform: "scale(0.96)" },
          "70%": { opacity: "0", transform: "scale(1.35)" },
          "100%": { opacity: "0", transform: "scale(1.35)" },
        },
        "sweep": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(300%)" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 1.6s cubic-bezier(0.2,0.7,0.4,1) infinite",
        sweep: "sweep 1.8s linear infinite",
        "fade-up": "fade-up 220ms ease-out both",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
