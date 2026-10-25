// SKELETON — re-verify on GB10 against docs.openclaw.ai before demo.
// Enforcement: before_tool_call -> PHANTOMSHIFT firewall; execute -> adapter submit only.

const ADAPTER_URL = "http://host.openshell.internal:7890/api/adapter/submit";
const FIREWALL_URL = "http://host.openshell.internal:7890/api/firewall/before_tool_call";
const AFTER_URL = "http://host.openshell.internal:7890/api/firewall/after_tool_call";
const TIMEOUT_MS = 10_000;
const MAX_RESPONSE_BYTES = 64 * 1024;
const REQUESTED_BY = "openclaw-agent";

const parameters = {
  type: "object",
  properties: {
    vendor_id: { type: "string", maxLength: 64 },
    invoice_id: { type: "string", maxLength: 64 },
    amount: { type: "integer", minimum: 1, description: "Integer CENTS." },
    currency: { type: "string", minLength: 3, maxLength: 3 },
    recipient_account_id: { type: "string", maxLength: 34 },
    evidence_spans: {
      type: "array",
      maxItems: 16,
      items: { type: "string", maxLength: 500 },
    },
    idempotency_key: { type: "string", maxLength: 128 },
  },
  required: [
    "vendor_id", "invoice_id", "amount", "currency",
    "recipient_account_id", "evidence_spans", "idempotency_key",
  ],
  additionalProperties: false,
};

function asResult(text, details) {
  return { content: [{ type: "text", text }], details };
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify(body),
    redirect: "error",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const raw = await res.text();
  if (raw.length > MAX_RESPONSE_BYTES) throw new Error("response too large");
  return { res, data: JSON.parse(raw) };
}

async function submit(params) {
  const body = {
    vendor_id: params.vendor_id,
    invoice_id: params.invoice_id,
    amount: params.amount,
    currency: params.currency,
    recipient_account_id: params.recipient_account_id,
    requested_by: REQUESTED_BY,
    evidence_spans: params.evidence_spans,
    idempotency_key: params.idempotency_key,
  };
  try {
    const { res, data: verdict } = await postJson(ADAPTER_URL, body);
    if (!res.ok || typeof verdict !== "object" || verdict === null || typeof verdict.state !== "string") {
      return asResult(`ERROR: unexpected adapter reply (HTTP ${res.status}).`, { state: "ERROR" });
    }
    return asResult(JSON.stringify(verdict), verdict);
  } catch (err) {
    const msg = `adapter unreachable: ${err && err.name ? err.name : "error"}`;
    return asResult(`ERROR: ${msg}`, { state: "ERROR", reason_code: "ADAPTER_UNREACHABLE" });
  }
}

const plugin = {
  id: "phantomshift-payment",
  name: "PHANTOMSHIFT Guarded Payment Tool",
  version: "0.2.0",
  description: "Finance-agent payment proposals enforced by PHANTOMSHIFT tool firewall.",
  register(api) {
    api.on("before_tool_call", async (event) => {
      const toolName = event.toolName || event.tool || "";
      try {
        const { data } = await postJson(FIREWALL_URL, {
          toolName,
          params: event.params || {},
          runId: event.runId,
          toolCallId: event.toolCallId,
        });
        if (data.block) {
          return { block: true, blockReason: data.blockReason || data.reason_code || "blocked by PHANTOMSHIFT" };
        }
      } catch (err) {
        return { block: true, blockReason: `PHANTOMSHIFT firewall unreachable: ${err.message || err}` };
      }
      return undefined;
    });

    api.registerTool({
      name: "phantomshift_submit_payment",
      label: "Propose Payment (guarded)",
      description:
        "Propose ONE invoice payment. Blocked at the firewall if vendor master, policy or allow-list rejects it.",
      parameters,
      async execute(_toolCallId, params) {
        const t0 = Date.now();
        let result;
        try {
          result = await submit(params ?? {});
          return result;
        } finally {
          try {
            const details = result?.details || {};
            await postJson(AFTER_URL, {
              toolName: "phantomshift_submit_payment",
              runId: _toolCallId,
              ok: details.state !== "ERROR",
              result_state: details.state,
              latency_ms: Date.now() - t0,
            });
          } catch {
            /* recorder best-effort */
          }
        }
      },
    });
  },
};

export default plugin;
