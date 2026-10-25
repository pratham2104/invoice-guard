// Halberd dashboard API (T03b): Express over the SQLite DB and the existing modules.
// Reads go through ./views.ts. Writes go ONLY through src/pipeline (ingest) and src/cases (human actions),
// so every control (human-only, manager-only approval, segregation of duties, state machine, audit chain) is
// the one those modules already enforce. There is deliberately no route that lets the model approve anything.
import { EventEmitter } from "node:events";
import { existsSync, readdirSync, rmSync, watch, type FSWatcher } from "node:fs";
import { basename, join } from "node:path";
import express, { type NextFunction, type Request, type Response } from "express";
import { openDb, loadFixtures, REPO_ROOT, type DB } from "../db/index.js";
import { processEml } from "../pipeline/index.js";
import { isLocalHost, localLlm } from "../fingerprint/index.js";
import * as cases from "../cases/index.js";
import { CaseCache, alertViews, caseDetail, listCaseViews, statusCounts, vendorViews } from "./views.js";

export const MODEL_ID = "nvidia/Qwen3.6-35B-A3B-NVFP4";

export interface ApiOptions {
  dbPath: string;                    // ":memory:" in tests
  inboxDir?: string;                 // default data/emails/incoming
  invoicesDir?: string;              // default data/invoices
  llmBaseUrl?: string | null;        // default process.env.LLM_BASE_URL; null/"" = rules only
  slackWebhookUrl?: string;          // default process.env.SLACK_WEBHOOK_URL; "" = never post
  fetchImpl?: typeof fetch;          // for the model probe and Slack (tests)
  corsOrigins?: string[];
  modelProbeMs?: number;
}

/** ControlError from src/cases → HTTP status. */
function controlStatus(msg: string): number {
  if (/^No such case/.test(msg)) return 404;
  if (/^Cannot |already/.test(msg)) return 409;
  return 403; // human-only, unknown user, wrong role, segregation of duties
}

class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export function createApi(opts: ApiOptions) {
  const inboxDir = opts.inboxDir ?? join(REPO_ROOT, "data", "emails", "incoming");
  const invoicesDir = opts.invoicesDir ?? join(REPO_ROOT, "data", "invoices");
  const llmBaseUrl = (opts.llmBaseUrl === undefined ? process.env.LLM_BASE_URL : opts.llmBaseUrl) || null;
  const slackWebhookUrl = opts.slackWebhookUrl ?? process.env.SLACK_WEBHOOK_URL ?? "";
  const doFetch = opts.fetchImpl ?? fetch;
  const paths = { inboxDir, invoicesDir };
  const cache = new CaseCache(paths);
  const events = new EventEmitter();
  events.setMaxListeners(0);

  let db: DB = openDb(opts.dbPath);
  if ((db.prepare("SELECT COUNT(*) AS n FROM vendors").get() as any).n === 0) loadFixtures(db);

  // One write at a time: processEml runs its own BEGIN/COMMIT on the shared handle.
  let chain: Promise<unknown> = Promise.resolve();
  function serial<T>(fn: () => Promise<T> | T): Promise<T> {
    const run = chain.then(fn, fn);
    chain = run.catch(() => undefined);
    return run;
  }

  // ---------------------------------------------------------------- model probe (cached briefly)
  let probe: { at: number; up: boolean } | null = null;
  async function modelUp(): Promise<boolean> {
    if (!llmBaseUrl) return false;
    try { if (!isLocalHost(new URL(llmBaseUrl).hostname)) return false; } catch { return false; }
    if (probe && Date.now() - probe.at < 10_000) return probe.up;
    let up = false;
    try {
      const res = await doFetch(`${llmBaseUrl.replace(/\/$/, "")}/models`, { signal: AbortSignal.timeout(opts.modelProbeMs ?? 1500) });
      up = res.ok;
    } catch { up = false; }
    probe = { at: Date.now(), up };
    return up;
  }

  // ---------------------------------------------------------------- inbox
  const state = { watching: false };
  const inboxFiles = () => (existsSync(inboxDir) ? readdirSync(inboxDir).filter((f) => f.endsWith(".eml") && !f.startsWith("._")).sort() : []);
  const processedFiles = () => new Map((db.prepare("SELECT file, outcome, case_id FROM processed_messages").all() as any[]).map((r) => [r.file, r]));

  function emit(type: "case" | "alert" | "status" | "reset", data: Record<string, unknown> = {}) {
    events.emit("event", { type, data });
  }

  /** Run one email through the real pipeline. `file` = a name in the inbox dir; omitted = next unprocessed. */
  function ingest(file?: string) {
    return serial(async () => {
      const done = processedFiles();
      const name = file ? basename(file) : inboxFiles().find((f) => !done.has(f));
      if (!name) throw new HttpError(409, "Every email in the inbox has already been processed. POST /api/demo/reset to start over.");
      const path = join(inboxDir, name);
      if (!name.endsWith(".eml") || !existsSync(path)) throw new HttpError(404, `No such inbox file: ${name}`);
      const up = await modelUp();
      const r = await processEml(db, path, {
        llm: up ? localLlm(llmBaseUrl!, process.env.LLM_MODEL ?? MODEL_ID) : false,
        slackWebhookUrl, fetchImpl: opts.fetchImpl,
      });
      const outcome = r.skipped ? ((processedFiles().get(name) as any)?.outcome ?? null) : r.decision!.outcome;
      if (r.caseId) {
        const hold = cases.getCase(db, r.caseId);
        await cache.invoice(db, hold);
        emit("case", { id: r.caseId });
      }
      if (r.alert && "id" in r.alert) emit("alert", { id: (r.alert as any).id });
      emit("status");
      return { processed: name, caseId: r.caseId, outcome, skipped: r.skipped, mode: up ? "model" : "rules-only" };
    });
  }

  let watcher: FSWatcher | null = null;
  const pending = new Set<string>();
  function startWatching() {
    if (watcher || !existsSync(inboxDir)) return;
    watcher = watch(inboxDir, (_ev, f) => {
      const name = f?.toString();
      if (!name || !name.endsWith(".eml") || name.startsWith("._") || pending.has(name)) return;
      pending.add(name);
      setTimeout(() => {   // let the writer finish the file
        pending.delete(name);
        if (!existsSync(join(inboxDir, name)) || processedFiles().has(name)) return;
        ingest(name).catch((err) => console.error(`[inbox] ${name}: ${(err as Error).message}`));
      }, 500);
    });
    state.watching = true;
  }
  function stopWatching() { watcher?.close(); watcher = null; state.watching = false; }

  function reset() {
    return serial(() => {
      db.close();
      if (opts.dbPath !== ":memory:") for (const s of ["", "-wal", "-shm", "-journal"]) rmSync(opts.dbPath + s, { force: true });
      db = openDb(opts.dbPath);
      const counts = loadFixtures(db);
      cache.clear();
      emit("reset");
      emit("status");
      return { ok: true, loaded: counts };
    });
  }

  // ---------------------------------------------------------------- app
  const app = express();
  app.disable("x-powered-by");
  const origins = new Set(opts.corsOrigins ?? ["http://localhost:5180", "http://127.0.0.1:5180"]);
  app.use((req, res, next) => {
    const o = req.headers.origin;
    if (o && origins.has(o)) {
      res.setHeader("Access-Control-Allow-Origin", o);
      res.setHeader("Vary", "Origin");
      res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
      res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    }
    if (req.method === "OPTIONS") { res.sendStatus(204); return; }
    next();
  });
  app.use(express.json({ limit: "32kb" }));

  const findHold = (id: string) => {
    const h = db.prepare("SELECT * FROM holds WHERE id = ?").get(id);
    if (!h) throw new HttpError(404, `No such case: ${id}`);
    return h as any;
  };
  const detail = (id: string) => caseDetail(db, cache, paths, findHold(id));
  const str = (v: unknown, name: string) => {
    if (typeof v !== "string" || !v.trim()) throw new HttpError(400, `"${name}" is required`);
    return v.trim();
  };
  const afterChange = (id: string) => { emit("case", { id }); emit("status"); };

  app.get("/api/status", async (_req, res) => {
    const up = await modelUp();
    res.json({
      product: "Halberd",
      org: "School District",
      model: { endpoint: llmBaseUrl, id: process.env.LLM_MODEL ?? MODEL_ID, up },
      mode: up ? "model" : "rules-only",
      cloudCalls: 0,
      inbox: { watching: state.watching, dir: inboxDir },
      sandbox: { name: "OpenShell", egress: "local only" },
      counts: await statusCounts(db, cache),
    });
  });

  app.get("/api/cases", async (_req, res) => { res.json(await listCaseViews(db, cache)); });
  app.get("/api/cases/:id", async (req, res) => { res.json(await detail(req.params.id)); });
  app.get("/api/alerts", (_req, res) => { res.json(alertViews(db)); });
  app.get("/api/vendors", (_req, res) => { res.json(vendorViews(db)); });
  app.get("/api/users", (_req, res) => {
    res.json(Object.entries(cases.users()).map(([id, role]) => ({ id, role: role === "ap_manager" ? "manager" : role === "ap_clerk" ? "clerk" : role })));
  });

  /**
   * Record the result of the out-of-band check. Phone callback for fraud holds (number on file only);
   * for requester holds the same route records the requester's yes/no. Starts verification first if needed.
   */
  app.post("/api/cases/:id/callback", async (req, res) => {
    const id = req.params.id;
    const result = req.body?.result;
    const actor = str(req.body?.actor, "actor");
    const note = typeof req.body?.note === "string" ? req.body.note : "";
    if (!["confirmed_fraud", "confirmed_legit", "no_answer"].includes(result)) {
      throw new HttpError(400, `"result" must be confirmed_fraud, confirmed_legit or no_answer`);
    }
    await serial(() => {
      const c = findHold(id);
      if (c.state === "OPEN") cases.startVerification(db, id, actor);
      if (result === "no_answer") {
        if (actor === cases.AGENT || !cases.users()[actor]) throw new cases.ControlError(`Unknown user '${actor}'.`);
        const now = cases.getCase(db, id);
        if (now.state !== "AWAITING_VENDOR" && now.state !== "AWAITING_REQUESTER") throw new cases.ControlError(`Cannot record a callback from state ${now.state}.`);
        if (now.state === "AWAITING_VENDOR") {
          db.prepare("UPDATE callbacks SET status = 'no_answer', outcome = ?, completed_at = NULL WHERE hold_id = ?").run(note || "no answer", id);
        }
        cases.addEvent(db, id, actor, "no_answer", { method: now.state === "AWAITING_VENDOR" ? "phone" : "requester", note });
      } else {
        cases.recordConfirmation(db, id, actor, result === "confirmed_legit", note);
      }
    });
    afterChange(id);
    res.json(await detail(id));
  });

  /** Clerks never approve or reject; the role claimed in the body is checked against the server's user list too. */
  function managerAction(kind: "approve" | "reject") {
    return async (req: Request, res: Response) => {
      const id = req.params.id as string;
      const actor = str(req.body?.actor, "actor");
      const role = req.body?.role;
      if (role !== "manager" && role !== "clerk") throw new HttpError(400, `"role" must be manager or clerk`);
      if (role === "clerk") throw new HttpError(403, `Only a manager can ${kind} a held payment.`);
      await serial(() => {
        findHold(id);
        if (kind === "approve") cases.approve(db, id, actor);
        else {
          const real = cases.users()[actor];
          if (actor === cases.AGENT || !real) throw new cases.ControlError(`Unknown user '${actor}'.`);
          if (!cases.APPROVER_ROLES.has(real)) throw new cases.ControlError(`${actor} (role: ${real}) is not allowed to reject.`);
          cases.reject(db, id, actor, typeof req.body?.reason === "string" ? req.body.reason : "");
        }
      });
      afterChange(id);
      res.json(await detail(id));
    };
  }
  app.post("/api/cases/:id/approve", managerAction("approve"));
  app.post("/api/cases/:id/reject", managerAction("reject"));

  app.post("/api/demo/reset", async (_req, res) => { res.json(await reset()); });
  app.post("/api/demo/ingest", async (req, res) => {
    const file = typeof req.body?.file === "string" && req.body.file ? req.body.file : undefined;
    res.json(await ingest(file));
  });
  app.get("/api/demo/files", (_req, res) => {
    const done = processedFiles();
    res.json(inboxFiles().map((f) => {
      const p = done.get(f) as any;
      return { file: f, processed: !!p, outcome: p?.outcome ?? null, caseId: p?.case_id ?? null };
    }));
  });

  app.get("/api/events", (req, res) => {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", Connection: "keep-alive" });
    res.write("retry: 2000\n\n");
    const send = (e: { type: string; data: unknown }) => res.write(`event: ${e.type}\ndata: ${JSON.stringify(e.data)}\n\n`);
    events.on("event", send);
    const beat = setInterval(() => res.write(": ping\n\n"), 15_000);
    req.on("close", () => { clearInterval(beat); events.off("event", send); });
  });

  app.use("/files/invoices", (req, res, next) => {
    if (!/\.pdf$/i.test(req.path)) { res.status(404).json({ error: "not found" }); return; }
    next();
  }, express.static(invoicesDir, { index: false, dotfiles: "deny", fallthrough: false }));

  app.use("/api", (_req, res) => { res.status(404).json({ error: "no such route" }); });

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof HttpError) { res.status(err.status).json({ error: err.message }); return; }
    if (err instanceof cases.ControlError) { res.status(controlStatus(err.message)).json({ error: err.message }); return; }
    if (err?.status && err.status < 500) { res.status(err.status).json({ error: err.message ?? "bad request" }); return; }
    console.error(err);
    res.status(500).json({ error: (err as Error)?.message ?? "internal error" });
  });

  return {
    app,
    events,
    ingest,
    reset,
    startWatching,
    stopWatching,
    get db() { return db; },
    close() { stopWatching(); events.removeAllListeners(); db.close(); },
  };
}
