/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: "#090D13", s1: "#111821", s2: "#17212B", s3: "#1B2733" },
        fg: { DEFAULT: "#F3F6F8", muted: "#A2AFBC", tertiary: "#788896" },
        stroke: { DEFAULT: "#263340", hover: "#405265" },
        chartreuse: "#C8FF69",
        coral: "#FF657A",
        cyan: "#70C7E6",
        amber: "#F4C17E",
        discord: "#8C97FF",
        graphite: { DEFAULT: "#090D13", panel: "#111821", raised: "#17212B" },
        ink: { primary: "#F3F6F8", secondary: "#A2AFBC", stroke: "#263340" },
        trace: "#70C7E6",
        danger: "#FF657A",
        ok: "#C8FF69",
        warn: "#F4C17E",
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "sans-serif"],
        mono: ["IBM Plex Mono", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: { panel: "14px" },
      transitionDuration: { DEFAULT: "200ms" },
    },
  },
  plugins: [],
};
