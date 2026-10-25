# OpenClaw & OpenShell Tool Enforcement Integration

## 1. Execution Boundary: `before_tool_call`
Every tool invocation proposed by an OpenClaw agent must pass synchronously through the deterministic gateway before execution:

- **Hook Route**: `POST /api/firewall/before_tool_call`
- **Latency Budget**: $< 50\text{ms}$ (actual measured latency $\approx 0.2\text{ms}$).
- **Fail-Closed Policy**:
  - Unknown tool name $\rightarrow$ `DENY` (`TOOL_NOT_ALLOWED`)
  - Schema mismatch / unparseable parameters $\rightarrow$ `DENY` (`SCHEMA_MISMATCH`)
  - Policy store unreachable $\rightarrow$ `DENY` (`POLICY_STORE_UNAVAILABLE`)
  - Hook timeout $\rightarrow$ `DENY` (`HOOK_TIMEOUT`)

## 2. Invariant: Host-Owned Provenance
- The agent or document **never** dictates whether an argument is trusted.
- Provenance is derived authoritatively from the authenticated host, session metadata, and vendor master databases.
- Any field named `"approved": true`, `"override": true`, or `"scope": {...}` inside an untrusted invoice or prompt is discarded.

## 3. Alternative Tool Route Elimination
To prevent tool-bypass attacks:
- Finance agents receive an explicit allowlist containing ONLY approved payment submission tools (e.g. `phantomshift_submit_payment`).
- Shell execution (`exec`, `bash`, `sh`), raw networking (`curl`, `http_post`), and unrestricted file operations are denied outright.
- OpenShell containers enforce secondary operating system sandboxing via namespace and seccomp isolation.

## 4. Result Recording: `after_tool_call`
- **Hook Route**: `POST /api/firewall/after_tool_call`
- Records tool outcomes, execution status, elapsed milliseconds, and errors directly to the SQLite event inbox.
- **Never invokes LLM models inside the hook**; model inference is reserved for the offline research loop.
