// npm run verify-local
import { existsSync } from "node:fs";
import { join } from "node:path";
import { REPO_ROOT } from "../db/index.js";
import { defaultCtx } from "./checks.js";
import { ARTIFACT, TICK, runAll, writeArtifact } from "./index.js";

const envFile = join(REPO_ROOT, ".env");
if (existsSync(envFile)) process.loadEnvFile(envFile);

const ctx = defaultCtx();
console.log(`Invoice Guard · local-inference proof · ${ctx.baseUrl} (${ctx.model})\n`);
const report = await runAll(ctx);
for (const c of report.results) console.log(`${TICK[c.status]} ${c.name}\n    ${c.detail}`);
writeArtifact(report);
const counts = report.results.reduce<Record<string, number>>((n, c) => ({ ...n, [c.status]: (n[c.status] ?? 0) + 1 }), {});
console.log(`\n${counts.pass ?? 0} passed · ${counts.fail ?? 0} failed · ${counts.warn ?? 0} warnings · ${counts.skip ?? 0} skipped · host ${report.host}`);
console.log(`Evidence: ${ARTIFACT.replace(REPO_ROOT + "/", "")}`);
process.exit(counts.fail ? 1 : 0);
