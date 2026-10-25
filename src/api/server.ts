// npm run api → Halberd dashboard API on PORT_API (default 4400).
// Loads .env like `npm run demo`; uses the same demo DB (DEMO_DB_PATH, default data/demo.db).
// The DB is kept across restarts; POST /api/demo/reset gives a fresh one.
import { existsSync } from "node:fs";
import { join } from "node:path";
import { REPO_ROOT } from "../db/index.js";
import { createApi } from "./app.js";

const envFile = join(REPO_ROOT, ".env");
if (existsSync(envFile)) process.loadEnvFile(envFile);

const dbPath = process.env.DEMO_DB_PATH ?? join(REPO_ROOT, "data", "demo.db");
const port = Number(process.env.PORT_API ?? 4400);
const host = process.env.HOST_API ?? "127.0.0.1";
const corsOrigins = process.env.CORS_ORIGINS?.split(",").map((s) => s.trim()).filter(Boolean);

const api = createApi({ dbPath, corsOrigins });
if (process.env.INBOX_WATCH !== "0") api.startWatching();

const server = api.app.listen(port, host, () => {
  console.log(`Halberd API on http://${host}:${port} · DB ${dbPath} · model ${process.env.LLM_BASE_URL ?? "off (rules only)"}` +
              ` · inbox watch ${process.env.INBOX_WATCH === "0" ? "off" : "on"}`);
});

const stop = () => { server.close(); api.close(); process.exit(0); };
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
