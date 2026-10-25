# OpenClaw / NemoClaw integration answers for PHANTOMSHIFT

Scope: resolve the "Still unknown" list in `docs/GB10_RUNBOOK.md` using only the pinned sources:
NVIDIA/NemoClaw `f00fb1d` (docs v0.0.137) at `REF = /home/923873155/Dell X NVIDIA Hack/refs/NemoClaw`,
plus `nemoclaw --help` / `openshell --help` output (CLI v0.0.137, OpenShell 0.0.116). Nothing here was run
against a sandbox: there is no sandbox on this host, and the OpenClaw runtime source (`openclaw`,
`@openclaw/discord`) is NOT in the pinned repo. Nothing in this directory is wired into `server.py` or any
existing file.

Tags used on every statement:

- **VERIFIED-IN-DOCS**: stated in a pinned `docs/*.mdx`, a shipped manifest/preset, or `--help` output.
- **VERIFIED-IN-SOURCE**: visible in pinned NemoClaw source or its test fixtures, not in prose docs.
- **INFERRED**: my reading of the above. Check on site.
- **UNKNOWN**: the pinned sources do not say. Section 6 lists what to read on site.

## 0. The three findings that matter most

1. **Use an OpenClaw native plugin to register the tool, and a SKILL.md to teach the model.** The only way
   to register a *structured* tool inside the sandbox is an agent-native OpenClaw plugin installed with
   `nemoclaw <name> exec -- openclaw plugins install <path>`. `nemoclaw <name> skill install <dir>` only
   adds a `SKILL.md` instruction directory (it registers no tool). Note the CLI verb is `skill`
   (singular), not `skills` as the runbook says. The plugin API belongs to OpenClaw, not NemoClaw, so it
   carries a compatibility risk. (Section 1.)
2. **A sandbox can reach a host service only through an explicit custom egress preset, and the safest form
   pins one host:port, one method, one exact path, and one binary.** Default policy is deny; nothing on the
   host is reachable. `host.docker.internal` is explicitly not supported. The docs' own recommended recipe is
   a custom preset on a non-loopback host IP; the shipped `observability-otlp-local` preset shows the
   `host.openshell.internal` pattern. Authenticated MCP rejects both host aliases. (Section 3.)
3. **The approval-by-reply path has a documented seam, the reaction path does not.** Discord user and guild
   allow-lists are enforced by OpenClaw's Discord plugin from config NemoClaw renders into `openclaw.json`
   (`allowFrom`, `guilds.<id>.users`). The only place the pinned source shows an authenticated sender id is a
   plugin **slash command** context (`senderId`, `channel`, `isAuthorizedSender`, `requireAuth`). Nothing in
   the pinned sources says tools receive the sender id or that OpenClaw delivers reaction events. Plan on
   text-message approval; treat reactions as UNKNOWN. (Section 2.)

## 1. Registering a custom tool or skill

### 1.1 Mechanisms found

| Mechanism | What it gives you | Fit | Tag |
|---|---|---|---|
| `nemoclaw <name> skill install <dir>` | Installs a `SKILL.md` directory (instructions + optional scripts). No tool is registered. | Good for guidance and a script fallback | VERIFIED-IN-DOCS |
| OpenClaw native plugin via `openclaw plugins install` | Code loaded by the OpenClaw gateway; can `registerTool`, `registerCommand`, `on("before_tool_call")` | Best fit for a typed, guarded tool | VERIFIED-IN-DOCS (lifecycle), VERIFIED-IN-SOURCE (API shape) |
| `nemoclaw <name> mcp add` | Registers a remote MCP server (HTTPS Streamable HTTP, bearer credential) in `openclaw.json` `mcp.servers` | Heavy: needs an HTTPS MCP server on a routed private address, a cert and a CA | VERIFIED-IN-DOCS |
| `onboard --agents agents.yaml` / `<name> agents apply -f` | Agent roster, per-agent model and `tools.allow/deny` policy, sub-agent delegation. Not tool registration | Useful only to restrict which tools the agent may call | VERIFIED-IN-DOCS |
| `onboard --from <Dockerfile>` | Replaces the whole sandbox image | Not needed; docs say do not bake plugins into an image to survive rebuilds | VERIFIED-IN-DOCS |

### 1.2 Skill: `nemoclaw <name> skill install <dir>`

- Command: `nemoclaw my-assistant skill install ./my-skill/`; list with `skill list`, remove with
  `skill remove <skill>`. `REF/docs/reference/commands.mdx:2871-2930`, and `nemoclaw --help` ("Skills:"). VERIFIED-IN-DOCS
- For OpenClaw this runs the unmodified `openclaw skills install <staged-path> --agent main --force`
  (`commands.mdx:2883`; `REF/agents/openclaw/manifest.yaml:49-52`). OpenClaw owns discovery, precedence and
  activation. NemoClaw keeps no inventory and does not claim the skill is active; confirm with
  `nemoclaw <name> skill list` and a new agent session. VERIFIED-IN-DOCS
- NemoClaw's own format check (the only part it enforces): the directory contains `SKILL.md` whose YAML
  frontmatter has a string `name` matching `[A-Za-z0-9._-]+`, at most 64 chars, not `.` or `..`.
  `REF/src/lib/skill-install.ts:28-50`, `REF/src/lib/skill-name.ts`. VERIFIED-IN-SOURCE
- Tree limits: at most 1,024 regular files and 64 MiB; names starting with `.` are skipped and listed;
  symlinks and special files are rejected; relative paths must match `[A-Za-z0-9._-/]`.
  `commands.mdx:2879-2891`, `skill-install.ts:58-120`. VERIFIED-IN-DOCS / VERIFIED-IN-SOURCE
- Fields beyond `name` (for example `description`) are the agent's Agent Skills convention; NemoClaw does not
  validate them. The skeleton includes `description`. INFERRED
- A plugin-shaped directory (contains `openclaw.plugin.json`) is refused with a hint. Keep the skill dir and
  the plugin dir separate. `REF/src/lib/actions/sandbox/skill-install.ts:67`. VERIFIED-IN-SOURCE
- OpenClaw scans skills before install; critical findings (direct process execution, env-var harvesting plus
  network, obfuscation, exfiltration patterns) block installation by default.
  `REF/docs/security/openclaw-controls.mdx:84-97`. VERIFIED-IN-DOCS. The bundled fallback script uses
  `urllib`, which could be flagged as "unexpected network activity"; if so, drop the script and rely on the
  plugin. INFERRED
- Where it lands: the manifest declares `/sandbox/.openclaw/workspace/skills` as the writable user-skill root
  (`manifest.yaml:50`); `skill remove` deletes `/sandbox/.openclaw/workspace/skills/<name>` (`commands.mdx:2924`).
  VERIFIED-IN-DOCS. Whether native `skills install` puts it in that same directory: INFERRED.

Skeleton: `skill/phantomshift-payment-guard/` (`SKILL.md` + `scripts/submit_payment.py`).

### 1.3 Plugin: the way to register an actual tool

Lifecycle (VERIFIED-IN-DOCS, `REF/docs/deployment/install-openclaw-plugins.mdx`):

```bash
# local path install needs no registry access; npm installs need: nemoclaw <name> policy add npm_registry --yes
nemoclaw <name> upload ./plugin/phantomshift-payment-tool /sandbox/phantomshift-payment-tool
nemoclaw <name> exec -- openclaw plugins install /sandbox/phantomshift-payment-tool
nemoclaw <name> exec -- openclaw plugins inspect phantomshift-payment --json
nemoclaw <name> gateway restart
nemoclaw <name> exec -- openclaw plugins inspect phantomshift-payment --runtime --json
```

- Stage the source outside `/sandbox/.openclaw/extensions/<plugin-id>`; use `--force` to replace a path
  install (`install-openclaw-plugins.mdx:42-46`). `nemoclaw <name> upload <host-path> [sandbox-dest]` exists in
  `nemoclaw --help`. VERIFIED-IN-DOCS
- NemoClaw's own live test installs with `HOME=/sandbox openclaw plugins install --force --accept-capabilities
  "$source_dir"` (`REF/test/e2e/live/full-e2e.test.ts:284`). The `--accept-capabilities` flag and `HOME=/sandbox`
  are not in prose docs. VERIFIED-IN-SOURCE (test), run `openclaw plugins install --help` on site.
- Plugin state survives restart, rebuild and restore (it lives in `/sandbox/.openclaw`); do not bake it into an
  image; do not hand-edit `openclaw.json` or the install index (`install-openclaw-plugins.mdx:85-104`).
  VERIFIED-IN-DOCS
- Files: `package.json` with `"openclaw": {"extensions": ["./index.js"]}` and `peerDependencies.openclaw`;
  `openclaw.plugin.json` with `id`, `name`, `version`, `description`, `activation.onStartup`,
  `contracts.tools: [<tool names>]`, `configSchema`; `index.js` default export with `register(api)` calling
  `api.registerTool({name, label, description, parameters (JSON schema), async execute(_toolCallId, params)})`
  returning `{content:[{type:"text", text}], details}`. Source of this shape: the dependency-free fixture
  `nativeWeatherPluginWriteScript` in `full-e2e.test.ts:222-286`; typed `defineToolPlugin` variant in
  `REF/test/e2e/fixtures/plugins/weather/src/index.ts`; schema `REF/schemas/openclaw-plugin.schema.json`.
  VERIFIED-IN-SOURCE (test fixtures only; the tool API is OpenClaw's contract, which is UNKNOWN to the pinned
  docs: `REF/docs/reference/extension-taxonomy-sdk-readiness.mdx:27,43`).
- A tool-call test hook exists: `POST http://127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18789}/tools/invoke` with
  body `{"agentId":"main","tool":"<name>","args":{...}}` and `Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN`
  (`full-e2e.test.ts:288-300`; token via `nemoclaw <name> gateway-token`). Useful to prove the tool is
  registered without involving the LLM. VERIFIED-IN-SOURCE (test), INFERRED that it works for our plugin.
- Plugin code runs inside the sandbox and is bound by its network policy
  (`install-openclaw-plugins.mdx:92-99`). Credentials never go in the plugin dir or `openclaw.json`. VERIFIED-IN-DOCS
- Hooks: NemoClaw's plugin registers `api.on("before_tool_call", ...)` and can return `{block, blockReason}`
  (`REF/nemoclaw/src/index.ts:140-153,264-300`). A PHANTOMSHIFT plugin could use the same hook as a second
  gate. VERIFIED-IN-SOURCE; behaviour in OpenClaw releases other than the pinned one: UNKNOWN.

Skeleton: `plugin/phantomshift-payment-tool/`. Syntax-checked, and exercised with a mock `api` against a local
stub server (a proposal with extra `approval_id`/`requested_by` fields was stripped; an unreachable endpoint
returned `ERROR`, never a payment state). Not run inside OpenClaw.

### 1.4 MCP (not recommended for us)

`nemoclaw <name> mcp add <server> --url https://... --env KEY [--deny-tool T] [--trusted-private-host H]`
writes `openclaw.json` `mcp.servers`, creates an OpenShell provider and generated egress policy.
`REF/docs/manage-sandboxes/add-mcp-server.mdx`. Constraints: HTTPS only, exactly one `--env` bearer, stdio
servers unsupported (`:249`), and **`host.openshell.internal`, `host.docker.internal`,
`host.containers.internal` and loopback are rejected** (`:223`, `:120`). A host MCP server needs an HTTPS
reverse proxy on a stable private address with a valid certificate (`:100-125`). `--deny-tool` matches tool
names only, not arguments (`:78-93`). All VERIFIED-IN-DOCS. Cost is high for a one-endpoint tool.

### 1.5 agents.yaml (`onboard --agents`, `<name> agents apply -f`)

Schema: `defaults.subagents.maxSpawnDepth`, `main.{tools,subagents}`, `agents[].{id,tools,model,description,subagents}`.
Each per-agent `tools` needs `{profile?, allow?, deny?}` with a non-empty `allow` or `deny`.
`REF/docs/inference/declarative-agents-manifest.mdx:55-135`. It does not register tools. It can restrict
`main` to an allow-list, which is how you would stop the model from calling anything but the guarded tool.
`agents apply` changes only the roster live; `main`/`tools`/`defaults` changes need
`onboard --agents <file> --recreate-sandbox` (`:180-198`). All VERIFIED-IN-DOCS. Whether `allow` entries use
plugin tool names verbatim: INFERRED.

### 1.6 Dockerfile `--from`

`nemoclaw onboard --from <Dockerfile>` replaces the whole image and must declare
`ARG NEMOCLAW_TOOL_DISCLOSURE=progressive` plus the matching `ENV` in the final stage; a custom image that
lacks the managed runtime (`/usr/local/bin/nemoclaw-start`, `/sandbox/.openclaw/openclaw.json`) is reported
as such (`commands.mdx:1047-1105`). Not needed for our tool, and the plugin docs say not to bake plugins in
(`install-openclaw-plugins.mdx:85-104`). VERIFIED-IN-DOCS. `--host-mount <host:/sandbox/path>` exposes a host
directory read-only under `/sandbox` (`nemoclaw onboard --help`); it is a one-way read path, not a way to
call a service. VERIFIED-IN-DOCS

### 1.7 Recommendation

1. `skill install` the `SKILL.md` (guidance; always documented, low risk).
2. Install the plugin for the real tool. If `registerTool` is rejected by the installed OpenClaw, fall back to
   the skill's `scripts/submit_payment.py`, which needs `exec` available to the agent and `python3` in the
   preset's `binaries` (INFERRED).
3. Optionally pin the agent to the guarded tool with `agents.yaml` `main.tools.allow` (then re-onboard).

## 2. Discord: inbound path, enforcement, sender identity, approval

### 2.1 Inbound message to agent turn

- NemoClaw writes the channel config into `openclaw.json` at image build time:
  `channels.discord.enabled`, `channels.discord.accounts.default.{enabled,dmPolicy,allowFrom,healthMonitor}`,
  `channels.discord.groupPolicy="allowlist"`, `channels.discord.guilds.<serverId>.{requireMention,users}`,
  `plugins.entries.discord.enabled`. It installs the pinned npm plugin `@openclaw/discord@<openclaw version>`
  and applies the `discord` network preset (required at create time). Source:
  `REF/src/lib/messaging/channels/discord/manifest.ts:5-215`, `template-resolver.ts`. VERIFIED-IN-SOURCE
- The bot token never enters the sandbox: the config carries the placeholder
  `openshell:resolve:env:DISCORD_BOT_TOKEN`; OpenShell rewrites it at egress, including inside the gateway
  WebSocket IDENTIFY frame (`policy/openclaw.yaml:29-47`, `manifest.ts:73-80`). VERIFIED-IN-SOURCE
- Egress for Discord is limited to `discord.com`, `gateway.discord.gg`, `*.discord.gg`,
  `cdn.discordapp.com`, `media.discordapp.net`, and only for `/usr/local/bin/node` and `/usr/bin/node`
  (`REF/src/lib/messaging/channels/discord/policy/openclaw.yaml`). VERIFIED-IN-SOURCE
- So the flow is: OpenClaw's Discord plugin (a node process in the sandbox) holds the gateway WebSocket,
  receives events, applies the allow-lists, and starts an agent turn. That the plugin receives MESSAGE_CREATE
  and runs a turn is INFERRED from the config and egress shape; the plugin's internals are not in the pinned
  repo (UNKNOWN). Troubleshooting confirms the gateway-connection requirement:
  `REF/docs/reference/troubleshooting.mdx:2382-2406`. VERIFIED-IN-DOCS
- NemoClaw's `channels add discord` health check ("startup, credential, or missing-plugin warnings") runs after
  rebuild (`add-channels-after-onboarding.mdx`). VERIFIED-IN-DOCS. `channels status --channel discord` has no
  documented runtime probe (only whatsapp, telegram, slack do); expect a registration/policy/config summary.
  INFERRED

### 2.2 Enforcement of `DISCORD_USER_ID`, `DISCORD_SERVER_ID`, `DISCORD_REQUIRE_MENTION`

Stated behaviour, `REF/docs/manage-sandboxes/set-up-discord.mdx:15-27` (VERIFIED-IN-DOCS):
mention-only by default; if `DISCORD_SERVER_ID` is set and `DISCORD_REQUIRE_MENTION` unset it defaults to `1`;
`0` replies to all messages in the server; `DISCORD_USER_ID` restricts access to one user; without it any
member of the configured server can message the bot.

Rendering (VERIFIED-IN-SOURCE, `template-resolver.ts:25-86`):

| Env | Rendered into `openclaw.json` |
|---|---|
| `DISCORD_SERVER_ID` (comma list OK; alias `DISCORD_SERVER_IDS`) | `channels.discord.groupPolicy="allowlist"`, `channels.discord.guilds.<id> = {requireMention, users?}`. With no server id, `guilds` is absent ("guild channels stay disabled", `manifest.ts:38`). |
| `DISCORD_REQUIRE_MENTION` (`0`/`1`, default `1`) | `guilds.<id>.requireMention` |
| `DISCORD_USER_ID` (comma list OK; alias `DISCORD_ALLOWED_IDS`) | `guilds.<id>.users=[ids]`, `accounts.default.allowFrom=[ids]`, `accounts.default.dmPolicy="allowlist"`. Absent: `dmPolicy` and `allowFrom` omitted. |

The code that actually drops a non-allowed sender is OpenClaw's Discord plugin; NemoClaw only renders config.
OpenClaw's own docs list "per-sender authorization" and four DM policy modes (open, disabled, pairing,
allowlist) (`openclaw-controls.mdx:99-110`), no detail. So: key names and rendering are VERIFIED-IN-SOURCE;
enforcement semantics are INFERRED from the key names and the NemoClaw prose. What `dmPolicy` defaults to when
`DISCORD_USER_ID` is unset: UNKNOWN. On-site check to prove enforcement: send as a second Discord account or
without a mention and confirm no turn starts (that test is the real proof).

Intents: the pinned docs never mention Discord Message Content or Server Members intents. UNKNOWN (the runbook
note that Message Content must be ON comes from our own setup notes, not the docs).

### 2.3 Can a skill or tool read reactions or the sender?

- Reactions: the only reaction mention in the pinned Discord material is network policy. The OpenClaw Discord
  preset allows `GET`/`POST`/`PUT`/`PATCH` on any path and `DELETE` on message and reaction paths
  (`policy/openclaw.yaml:19-27`), so reaction REST calls are not blocked at the network layer. VERIFIED-IN-SOURCE.
  Whether OpenClaw subscribes to reaction events, exposes them to the agent, or has a reaction tool: **UNKNOWN**.
  (Hermes config has `reactions: true`, `manifest.ts:~183`; that is Hermes only.)
- Sender identity, slash command path: a plugin command registered with `api.registerCommand({name,
  description, acceptsArgs, requireAuth, handler(ctx)})` receives `ctx = {senderId?, channel,
  isAuthorizedSender, args, commandBody, config, from?, to?, accountId?}`. `REF/nemoclaw/src/index.ts:68-91,
  231-236`. VERIFIED-IN-SOURCE (NemoClaw's local typing of OpenClaw's plugin API). `/nemoclaw status` is
  documented as available "inside the OpenClaw chat interface" (`commands.mdx:72-80`) but whether
  OpenClaw routes Discord messages starting with `/` to plugin commands, and whether `senderId` is the Discord
  snowflake string: UNKNOWN.
- Sender identity, tool path: the weather fixture's `execute(_toolCallId, params)` receives no sender context;
  `before_tool_call` events carry `toolName, params, runId?, toolCallId?` only (`index.ts:140-146`).
  VERIFIED-IN-SOURCE for what NemoClaw uses; whether richer context exists: UNKNOWN. A model-called tool must
  not be trusted to report who approved.
- Session logs: `/sandbox/.openclaw/agents/main/sessions/<id>.jsonl` holds assistant messages and tool
  calls/results (`monitor-sandbox-activity.mdx:65-75`). VERIFIED-IN-DOCS. Whether the sender id appears there: UNKNOWN.

### 2.4 Approval by message reply

- VERIFIED-IN-DOCS: nothing in the pinned docs describes an approval flow via channel replies. OpenClaw has a
  "plugin approval" workflow that defaults to deny on timeout (`openclaw-controls.mdx:43`); details UNKNOWN.
- INFERRED design that fits what exists: keep approval authority OUT of the model. The operator's
  `approve <nonce> <digest>` message must be matched to the authenticated sender by trusted code. Candidate
  seams, best first: (a) a plugin slash command (has `senderId` + `isAuthorizedSender`) that POSTs to a
  separate host endpoint and returns the result; (b) the existing out-of-band path in
  `phantomshift/discord_auth.py` fed by a trusted event source, not by the model; (c) a model-called tool
  (weakest, the model controls its arguments). Do not add an approval endpoint to the sandbox-reachable
  preset; the preset in `policy/` allows only `POST /api/adapter/submit`.
- Answer to the runbook's third question ("channel handler or a tool"): NemoClaw offers no hook into the
  OpenClaw channel handler; channels are built-in manifests, "not an external plugin API"
  (`extension-taxonomy-sdk-readiness.mdx:59`). VERIFIED-IN-DOCS. So the gate cannot sit in the channel
  handler; it sits in a plugin tool (submission), with approval resolved server-side. INFERRED.

## 3. Reaching a host service from the sandbox

### 3.1 Default

Deny by default. The OpenClaw baseline (`REF/nemoclaw-blueprint/policies/openclaw-sandbox.yaml`) lists only
`integrate.api.nvidia.com`, `inference.local`, `clawhub.ai`, `openclaw.ai`, `catalog.openclaw.ai`,
`docs.openclaw.ai`, `registry.npmjs.org`; header: "deny by default" (`:3-5`). No host service is allowed.
VERIFIED-IN-DOCS. Blocked requests show in `openshell term` with host, port, binary, method, path
(`REF/docs/network-policy/approve-network-requests.mdx`). VERIFIED-IN-DOCS. Note the baseline `nvidia` entry
allows `integrate.api.nvidia.com` for `/usr/local/bin/openclaw` regardless of the inference route (relevant to
H03, section 4).

### 3.2 Supported ways, from least to most invasive

1. **Custom preset with exact rules (recommended).** `nemoclaw <name> policy add --from-file preset.yaml
   [--trusted-private-host <exact-host-or-ip>] --dry-run` then without `--dry-run`. The docs' own host-service
   recipe: expose the service on a host IP the OpenShell gateway can reach (not loopback-only), one preset
   with exact host, port, `rules: allow {method, path}` and `binaries`; the policy is merged into the live
   policy and survives rebuild. `REF/docs/reference/troubleshooting.mdx:2540-2602`,
   `customize-network-policy.mdx:29-38`, `create-custom-policy-presets.mdx:22-96`. VERIFIED-IN-DOCS
2. **`host.openshell.internal` with `allowed_ips`.** Custom presets must not declare `allowed_ips` except for
   the endpoint host `host.openshell.internal` (`create-custom-policy-presets.mdx:68`;
   `REF/src/lib/policy/index.ts:251-283`). Shipped presets use it:
   `observability-otlp-local.yaml` (`POST /v1/traces` only, one binary) and `local-inference.yaml`.
   VERIFIED-IN-SOURCE. NemoClaw's Dockerfile comment states users "legitimately reach host-local approved
   services through host.openshell.internal after the OpenShell policy explicitly allows that host:port"
   (`REF/Dockerfile:1146-1153`). VERIFIED-IN-SOURCE. But troubleshooting says these names "are not guaranteed
   to point at a reachable host gateway" (`troubleshooting.mdx:2544`). Both are in the pinned docs; treat
   reachability as something to prove on site with `getent hosts host.openshell.internal` inside the sandbox.
3. `openshell term` interactive approve (`a`): session-only, resets on recreate, not persisted
   (`approve-network-requests.mdx`). VERIFIED-IN-DOCS. Good for discovering the binary path, not for the demo.
4. `openshell policy set` replaces the whole live policy; use only with a reviewed full document
   (`apply-policy-presets.mdx` warning). VERIFIED-IN-DOCS. `openshell policy update --add-endpoint ...` and
   `--add-allow` exist in `openshell policy --help` examples; not covered by NemoClaw docs. UNKNOWN fit.
5. Do NOT: `host.docker.internal` ("bypasses the OpenShell policy path"), `curl --noproxy '*'` (bypasses
   enforcement and audit), `personal_open_internet` preset, `mcp add` to a host alias (rejected).

### 3.3 Safest concrete form (skeleton in `policy/phantomshift-adapter-preset.yaml`)

- One endpoint, one port, `POST` only, exact path `/api/adapter/submit` (no `/**`). The sandbox then cannot
  reach any approval, replay or admin route on the same listener.
- `binaries`: only the process that makes the call. Plugin path: the gateway's node (`/usr/local/bin/node`
  per other presets; confirm in `openshell term`). Remove `/usr/bin/python3` unless using the skill fallback.
  A preset endpoint with no matching binary authorizes nothing (`create-custom-policy-presets.mdx` end of the
  MCP recipe). VERIFIED-IN-DOCS
- `allowed_ips` narrowed to the single bridge address (INFERRED that a `/32` is accepted: the source only checks
  that the key exists on the bridge host).
- Port: avoid NemoClaw's reserved or default ports 8000, 8080, 8081, 8642-8652, 8990-9005, 11434-11438, 4318,
  18789-18799 (`REF/src/lib/core/protected-host-ports.ts`, `local-inference.yaml`). Note `local-inference`
  opens 8000/8081/11434/11435 to `curl`, `node`, `python3` with `GET/POST /**`; do not put the adapter on
  those ports, and apply `local-inference` only if you need it. VERIFIED-IN-SOURCE
- The host listener must bind the bridge gateway address (or the chosen private IP), NOT `0.0.0.0` and NOT
  loopback only (the docs require reachability from a host IP, "not only from 127.0.0.1", `troubleshooting.mdx:2546`; sandbox loopback is not the host, `add-mcp-server.mdx:120-121`). `server.py`
  today is loopback-only, so this is a separate listener. Use a host firewall to allow only the OpenShell
  Docker subnet, as the vLLM docs advise for bearerless host services (`set-up-vllm.mdx` warning).
  VERIFIED-IN-DOCS (advice), INFERRED (application here).
- SSRF guard: a policy match does not bypass OpenShell's private-address checks; the diagnostic ladder is
  `policy_denied` (preset/binary mismatch) versus `upstream_unreachable` (policy matched, gateway cannot reach
  the host IP:port) (`troubleshooting.mdx:2602`). VERIFIED-IN-DOCS
- Remember the sandbox, and the model, can forge any request to this endpoint. The adapter must stay
  fail-closed and must treat every body as untrusted (it already validates schema, vendor, recipient binding,
  cap, idempotency; `phantomshift/adapter.py`). Approval ids must never be obtainable through this route.

### 3.4 Endpoint contract (to be implemented by the lead; NOT implemented here)

`POST /api/adapter/submit`, `Content-Type: application/json`, body is the untrusted proposal as accepted by
`ProposedPayment.from_untrusted`:

```json
{"vendor_id":"v-acme","invoice_id":"inv-1001","amount":123456,"currency":"USD",
 "recipient_account_id":"ACC123","requested_by":"openclaw-agent",
 "evidence_spans":["Pay to ACC123"],"idempotency_key":"inv-inv-1001"}
```

- `amount` integer cents. `approval_id` is optional in the schema, but the sandbox-facing tool and script never
  send it; resubmission with an approval id is a trusted, operator-side action.
- Reply: HTTP 200 with the adapter result object for ANY adapter decision, including `DENIED`
  (`state` is one of `DENIED | PENDING_APPROVAL | EXECUTED_SIMULATED`, plus `reason_code`, `reason`,
  `executed_simulated`, `simulated`, `label`, `evidence`, `mode`). The tool and script treat non-200, non-JSON,
  missing `state`, redirects, bodies over 64 KiB and timeouts (10 s) as `ERROR` and never as a payment state.
- Suggested server rules: method `POST` only; reject other paths; body limit 64 KiB; JSON object only; reply
  `state` verbatim from `PaymentAdapter.submit`; log every request with a hash chain entry; no CORS; no
  approval-granting route on this listener.

## 4. Inference routing and the H03 proof

- Where it lives: new OpenClaw selections for Ollama, standalone vLLM and llama.cpp use a sandbox-attached
  OpenShell provider for the qualified host-local endpoint (recorded as
  `http://host.openshell.internal:<port>/v1` for a bearerless server, default vLLM port 8000); other routes
  use the shared `inference.local` route that OpenShell proxies. `REF/docs/inference/how-inference-routing-works.mdx`
  (Request Path, Credential Boundary), `set-up-vllm.mdx` (warning block). VERIFIED-IN-DOCS. Where the docs
  say the OpenClaw route "remains `https://inference.local` inside the sandbox" (`set-up-vllm.mdx`, openclaw
  variant), the two statements conflict for OpenClaw + vLLM; which one applies on the GB10 is UNKNOWN, so
  record whatever `inference get` prints.
- Read the route: `nemoclaw inference get [--json]` prints provider, model and endpoint without sending a
  request (`REF/docs/inference/view-active-inference-route.mdx`). Expected shape (example given for NVIDIA):
  `Provider: ...  Model: ...  Endpoint: ...`. For local vLLM the docs name the provider `vllm-local`
  (`set-up-vllm.mdx`, "Accept the result when `nemoclaw list` reports ... provider `vllm-local`"). The exact
  `inference get` text for vLLM is not shown in the docs. UNKNOWN until run.
- Prove it works: `nemoclaw <name> status` probes the in-sandbox route and sends a real inference request;
  for local vLLM it also prints host-side backend diagnostics (`verify-inference-route.mdx`,
  `monitor-sandbox-activity.mdx`). VERIFIED-IN-DOCS
- Prove no hosted route: `nemoclaw credentials list` shows stored providers; `openshell inference get`
  shows the gateway-level route; `openshell term` and `nemoclaw <name> logs` show actual egress.
  `nemoclaw --help`, `openshell inference --help`. VERIFIED-IN-DOCS (commands exist), INFERRED (as evidence).
- Caveat for R01: the baseline policy still allows `integrate.api.nvidia.com` for the openclaw binary
  (`openclaw-sandbox.yaml:66-77`). Credentials stay on the host, and a local route does not use it, but the
  permission exists. `nemoclaw <name> policy exclude <key> --dry-run` can remove a baseline entry, but it
  refuses entries without a reviewed impact disclosure (`commands.mdx:2430-2438`); whether `nvidia` is
  excludable: UNKNOWN, run `--dry-run`.
- `scripts/verify_hackathon.py` H03 reads `nemoclaw inference get --json` as free text and looks for
  `vllm|llama|inference.local|host.openshell.internal|127.0.0.1|localhost` and for hosted words. A route
  printed as provider `vllm-local` passes that check; `inference.local` alone does not prove the backend is
  local (it also fronts hosted shared routes), so save the full `inference get --json`, `status` and
  `credentials list` outputs as the evidence, not just the grep result. INFERRED

## 5. Answers to the three runbook unknowns

1. **How to register the guarded payment tool.** Plugin (`registerTool`) for the tool, `skill install` for the
   `SKILL.md`; `mcp add` and `--from` are the wrong tools; `agents.yaml` only restricts. Section 1.
2. **Reactions versus message reply.** Reactions: UNKNOWN (OpenClaw side, not in pinned sources). Message
   reply: the only documented building block is a plugin slash command context carrying `senderId` and
   `isAuthorizedSender`; whether Discord messages reach it is UNKNOWN. Section 2.
3. **Channel handler or tool for the nonce/approval gate.** Not the channel handler (no extension point). The
   submission goes through a tool; the approval must be resolved by trusted code outside model control.
   Section 2.4.

## 6. UNKNOWN list and what to read on site

| # | UNKNOWN | Read or run on site |
|---|---|---|
| 1 | OpenClaw plugin tool API contract (`registerTool` shape, versioning, `--accept-capabilities`) | `nemoclaw <name> exec -- openclaw plugins install --help`; https://docs.openclaw.ai (plugins, tools); `openclaw plugins inspect phantomshift-payment --runtime --json` |
| 2 | Whether `skills install` and the plugin scanner accept our skill and plugin | Output of `skill install`; `openclaw security audit` |
| 3 | Discord: how the plugin applies `allowFrom`, `users`, `requireMention`; default `dmPolicy`; required intents | https://docs.openclaw.ai (channels/discord); negative tests from a second account and without a mention |
| 4 | Whether OpenClaw delivers reaction events or has a reaction tool | docs.openclaw.ai Discord page; `openclaw agent --help`; `openclaw tools list` style commands if present |
| 5 | Whether tools or `before_tool_call` receive the sender id; whether Discord text starting with `/` hits plugin commands; exact meaning of `senderId` | docs.openclaw.ai plugin hooks and commands; test with a throwaway `registerCommand` that echoes `ctx` fields (no secrets) |
| 6 | Whether `host.openshell.internal` resolves and is reachable for our port on the GB10; exact bridge IP; which binary makes the call | `nemoclaw <name> exec -- getent hosts host.openshell.internal`; `openshell term` after one blocked attempt; `policy add --dry-run` output |
| 7 | Whether `--trusted-private-host` is needed for the bridge name, and whether `/32` in `allowed_ips` is accepted | `policy add --from-file ... --dry-run` |
| 8 | Exact `nemoclaw inference get` text for local vLLM with OpenClaw, and whether the route is `inference.local` or `host.openshell.internal` | `nemoclaw inference get --json` after onboarding |
| 9 | Whether baseline `nvidia` egress entry can be excluded | `nemoclaw <name> policy exclude nvidia --dry-run` |
| 10 | `skill install` landing directory and the agent's cwd for the fallback script path | `nemoclaw <name> exec -- ls /sandbox/.openclaw/workspace/skills`; `skill list` |
| 11 | Whether Node `fetch` with the sandbox's env-proxy reaches a plain-HTTP private IP through the OpenShell proxy | `curl` through `/tools/invoke` (section 1.3) then `openshell term`; fall back to the python script |
| 12 | Whether the Discord channel can be driven non-interactively (`channels add discord` prompts) | `NEMOCLAW_NON_INTERACTIVE=1 ... channels add discord` per `add-channels-after-onboarding.mdx`; do on site, never with a pasted token in argv |

## 7. Files in this directory

| Path | What |
|---|---|
| `README.md` | this document |
| `ONSITE_CHECKLIST.md` | verification commands and expected evidence for H03, H04, H05 |
| `skill/phantomshift-payment-guard/SKILL.md` | NemoClaw `skill install` format; instructions for the model |
| `skill/phantomshift-payment-guard/scripts/submit_payment.py` | stdlib fallback client for `POST /api/adapter/submit` |
| `plugin/phantomshift-payment-tool/` | OpenClaw native plugin skeleton registering `phantomshift_submit_payment` |
| `policy/phantomshift-adapter-preset.yaml` | custom egress preset (one host, one port, `POST /api/adapter/submit`) |
