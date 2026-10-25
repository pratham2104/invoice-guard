import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = process.env.HALBERD_API ?? "http://localhost:4400";
const PORT = Number(process.env.PORT_WEB ?? 5180);

export default defineConfig({
  plugins: [react()],
  server: {
    port: PORT,
    strictPort: true,
    proxy: {
      "/api": { target: API, changeOrigin: true },
      "/files": { target: API, changeOrigin: true },
    },
  },
  preview: { port: PORT },
});
