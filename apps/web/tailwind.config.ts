import type { Config } from "tailwindcss";

/**
 * One design system, defined once.
 *
 * The rule that shapes the palette: saturated green, amber and red are
 * reserved *exclusively* for verdicts (ALLOW / REQUIRE_APPROVAL / BLOCK).
 * Nothing else in the product is allowed to use them, so a colour in this UI
 * always means the same thing. The accent is indigo precisely because it sits
 * outside that family and can never be mistaken for a decision.
 */
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        /** Top navigation only. */
        chrome: {
          DEFAULT: "#141C2E",
          text: "#A8B2C4",
          bright: "#FFFFFF",
        },
        canvas: "#F6F7F9",
        surface: {
          DEFAULT: "#FFFFFF",
          sunken: "#FAFBFC",
        },
        line: {
          DEFAULT: "#E3E6EB",
          strong: "#D2D7E0",
        },
        ink: {
          DEFAULT: "#1A2233",
          secondary: "#5A6577",
          muted: "#8A93A3",
        },
        accent: {
          DEFAULT: "#4F46E5",
          hover: "#4338CA",
          tint: "#EEF0FE",
          onDark: "#6366F1",
        },
        /** Verdicts. Reserved. */
        allow: {
          DEFAULT: "#0F7A4E",
          tint: "#E8F4EE",
          line: "#AFD9C4",
        },
        approval: {
          DEFAULT: "#9A5B00",
          tint: "#FCF2E2",
          line: "#EFD2A2",
        },
        block: {
          DEFAULT: "#C2334A",
          tint: "#FCEBEE",
          line: "#F0BFC8",
        },
        inactive: {
          DEFAULT: "#94A3B8",
          tint: "#F1F5F9",
          line: "#E2E8F0",
        },
        /** Sandbox / offline notices. Deliberately NOT amber — amber is a verdict. */
        notice: {
          DEFAULT: "#2C3A52",
          tint: "#EEF1F6",
          line: "#D3DAE6",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        // The scale, used everywhere. Nothing renders at an ad-hoc size.
        "label": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.06em", fontWeight: "500" }],
        "data": ["0.78125rem", { lineHeight: "1.15rem" }],
        "caption": ["0.8125rem", { lineHeight: "1.25rem" }],
        "body": ["0.875rem", { lineHeight: "1.55" }],
        "section": ["0.9375rem", { lineHeight: "1.4rem", fontWeight: "600" }],
        "title": ["1.5rem", { lineHeight: "2rem", letterSpacing: "-0.01em", fontWeight: "600" }],
        "display": ["2rem", { lineHeight: "2.5rem", letterSpacing: "-0.02em", fontWeight: "600" }],
      },
      borderRadius: {
        panel: "8px",
        control: "6px",
      },
      boxShadow: {
        card: "0 1px 2px rgb(16 24 40 / 0.04), 0 1px 3px rgb(16 24 40 / 0.06)",
        raised: "0 4px 12px rgb(16 24 40 / 0.08), 0 1px 3px rgb(16 24 40 / 0.06)",
      },
      spacing: {
        // 8px rhythm; the odd values below exist only for optical alignment.
        "4.5": "1.125rem",
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(3px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-soft": "pulse-soft 1.6s ease-in-out infinite",
        "fade-up": "fade-up 200ms ease-out both",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
