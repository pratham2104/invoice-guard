/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: "#070B10", s1: "#0D131C", s2: "#141D2B", s3: "#1C283B" },
        fg: { DEFAULT: "#F0F6FC", muted: "#8B9BB4", tertiary: "#566B82" },
        stroke: { DEFAULT: "#1F2E42", hover: "#334B6B" },
        halberd: {
          green: "#00F59B",
          cyan: "#00D4FF",
          red: "#FF3B5C",
          amber: "#F59E0B",
          purple: "#A855F7",
        },
        chartreuse: "#00F59B",
        coral: "#FF3B5C",
        cyan: "#00D4FF",
        amber: "#F59E0B",
        slack: {
          aubergine: "#4A154B",
          yellow: "#ECB22E",
          blue: "#36C5F0",
          green: "#2EB67D",
          red: "#E01E5A",
        },
        discord: "#8C97FF",
        graphite: { DEFAULT: "#070B10", panel: "#0D131C", raised: "#141D2B" },
        ink: { primary: "#F0F6FC", secondary: "#8B9BB4", stroke: "#1F2E42" },
        trace: "#00D4FF",
        danger: "#FF3B5C",
        ok: "#00F59B",
        warn: "#F59E0B",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: { panel: "12px" },
      boxShadow: {
        glowGreen: "0 0 25px -5px rgba(0, 245, 155, 0.35)",
        glowCyan: "0 0 25px -5px rgba(0, 212, 255, 0.35)",
        glowRed: "0 0 25px -5px rgba(255, 59, 92, 0.35)",
      },
      transitionDuration: { DEFAULT: "180ms" },
    },
  },
  plugins: [],
};
