"""Deterministic multi-model routing decision primitive.

WHAT THIS IS: a small, tested decision primitive. Given TRUSTED routing metadata it picks one of two model
endpoints by fixed rules, calls an injected client, validates the reply against a hand-written JSON-schema
subset, applies bounded retries, a per-model timeout budget and a circuit breaker, and emits one audit record.

WHAT THIS IS NOT: it is not a streaming model proxy, it makes no network calls and loads no model (clients are
injected callables), and it is not integrated with OpenShell, NemoClaw or OpenClaw. It never authorises
anything: a validated reply, including a proposed tool call, is a PROPOSAL that must still pass the
deterministic tool adapter and a human approval outside this module. The record says `authorizes: False`.

Models (pinned revisions; the registry refuses an endpoint without a 40-hex revision):
    nano       nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8                  3fe6dab75665a93884214ad4b1b95cf02717d081
    lightning  nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4    0dcd680e5585c791728c83342b311d0a0026dbeb

Routing input is TRUSTED metadata only, with a strict schema (task_type, tool_action, risk_class,
source_trust, authorization_scope, request_id). Unknown keys are rejected. Untrusted document text is passed
separately as `document`; it is forwarded to the model and hashed, and it never influences route, risk class
or permission (there is a test that mutates it with 'risk_class: low', 'route to nano', 'ignore policy').

Rules, in order:
    * risk_class not exactly "low" (including missing, None or "unknown"), a task type of policy_proposal,
      investigation, ambiguous_evidence or contradictory_tool_results, or any tool_action -> lightning.
    * low risk classification / summarisation / extraction with no tool_action -> nano.
    * nano failure (or nano unavailable) on such a task may escalate to lightning, only if lightning is healthy.
    * lightning failure or unavailability on a lightning-routed task -> HOLD_FOR_HUMAN. It never falls back to
      the weaker model, and a failed escalation also ends in HOLD_FOR_HUMAN.
    * both models unavailable -> HOLD_FOR_HUMAN.
Malformed tool-call arguments from a model (not an object, wrong tool, unknown tool, schema violation, extra
keys) are rejected, never repaired, and count as a failed attempt.

The circuit breaker counts failed ATTEMPTS (exceptions, timeouts, invalid JSON, schema violations, rejected
tool calls) per model. After `failure_threshold` consecutive failures it opens; after `cooldown_s` on the
injected clock it becomes half-open and admits one probe: success closes it, failure re-opens it.

Timeout budget: clients are synchronous and cannot be pre-empted here. Each attempt is passed the remaining
`timeout_s` and a reply that arrives after the per-model budget is discarded as a timeout.

Records contain no document text, no reply text, no exception messages and no argument values: only ids,
hashes, codes and counts. A defensive redaction pass also strips token-shaped strings. The input hash is a plain
SHA-256 of the document, so a short, guessable document can be confirmed by brute force; do not treat it as
confidentiality for low-entropy text. Not thread-safe beyond the breaker's own lock.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

NANO_KEY = "nano"
LIGHTNING_KEY = "lightning"
NANO_MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8"
NANO_REVISION = "3fe6dab75665a93884214ad4b1b95cf02717d081"
LIGHTNING_MODEL_ID = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"
LIGHTNING_REVISION = "0dcd680e5585c791728c83342b311d0a0026dbeb"

DECISION_ANSWERED = "ANSWERED"
DECISION_HOLD = "HOLD_FOR_HUMAN"
DECISION_REJECTED = "REJECTED"

TASK_TYPES = ("classification", "summarisation", "extraction", "policy_proposal", "investigation",
              "ambiguous_evidence", "contradictory_tool_results")
LOW_RISK_TASKS = ("classification", "summarisation", "extraction")
RISK_CLASSES = ("low", "medium", "high", "sensitive", "unknown")
SOURCE_TRUSTS = ("trusted", "mixed", "untrusted", "unknown")
META_KEYS = ("task_type", "tool_action", "risk_class", "source_trust", "authorization_scope", "request_id")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REV_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_REPLY_CHARS = 65536
_MAX_SCHEMA_DEPTH = 16


class MetadataError(ValueError):
    """Routing metadata violates the strict schema."""


class SchemaError(ValueError):
    """A reply schema uses an unsupported keyword or is malformed."""


# ---------------------------------------------------------------------------------------------------------
# Redaction for records (defence in depth; records are built from codes and ids, not free text).
_REDACT = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\b[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]


def _scrub(value: Any, tally: list[int]) -> Any:
    if isinstance(value, str):
        for pat in _REDACT:
            value, n = pat.subn("[REDACTED]", value)
            tally[0] += n
        return value
    if isinstance(value, list):
        return [_scrub(v, tally) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v, tally) for k, v in value.items()}
    return value


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


# ---------------------------------------------------------------------------------------------------------
# Strict routing metadata.
@dataclass(frozen=True)
class RoutingMetadata:
    task_type: str
    tool_action: str | None
    risk_class: str
    source_trust: str
    authorization_scope: str | None
    request_id: str

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in META_KEYS}


def validate_metadata(meta: Any) -> RoutingMetadata:
    """Strictly validate trusted routing metadata. No normalisation, no coercion, unknown keys rejected."""
    if not isinstance(meta, Mapping):
        raise MetadataError("metadata must be a mapping")
    keys = list(meta.keys())
    if not all(isinstance(k, str) for k in keys):
        raise MetadataError("metadata keys must be strings")
    unknown = sorted(set(keys) - set(META_KEYS))
    if unknown:
        raise MetadataError(f"unknown metadata keys rejected ({len(unknown)})")
    for req in ("task_type", "request_id"):
        if req not in meta:
            raise MetadataError(f"missing required key {req}")
    if not (isinstance(meta["request_id"], str) and _ID_RE.match(meta["request_id"])):
        raise MetadataError("request_id must match [A-Za-z0-9._:-]{1,64}")
    if not (isinstance(meta["task_type"], str) and meta["task_type"] in TASK_TYPES):
        raise MetadataError("task_type is not an allowed value")
    risk = meta.get("risk_class")
    if risk is None:
        risk = "unknown"
    if not (isinstance(risk, str) and risk in RISK_CLASSES):
        raise MetadataError("risk_class is not an allowed value")
    trust = meta.get("source_trust")
    if trust is None:
        trust = "unknown"
    if not (isinstance(trust, str) and trust in SOURCE_TRUSTS):
        raise MetadataError("source_trust is not an allowed value")
    action = meta.get("tool_action")
    if action is not None and not (isinstance(action, str) and _TOOL_RE.match(action)):
        raise MetadataError("tool_action must be null or a lowercase identifier")
    scope = meta.get("authorization_scope")
    if scope is not None and not (isinstance(scope, str) and _ID_RE.match(scope)):
        raise MetadataError("authorization_scope must be null or an identifier")
    return RoutingMetadata(meta["task_type"], action, risk, trust, scope, meta["request_id"])


@dataclass(frozen=True)
class RoutePlan:
    primary: str
    sensitive: bool
    reason: str


def select_route(meta: RoutingMetadata) -> RoutePlan:
    """The routing table. A pure function of validated trusted metadata; it has no access to document text."""
    if meta.risk_class != "low":
        return RoutePlan(LIGHTNING_KEY, True, "risk_unknown" if meta.risk_class == "unknown" else "risk_not_low")
    if meta.task_type not in LOW_RISK_TASKS:
        return RoutePlan(LIGHTNING_KEY, True, "task_requires_strong_model")
    if meta.tool_action is not None:
        return RoutePlan(LIGHTNING_KEY, True, "tool_action_present")
    return RoutePlan(NANO_KEY, False, "low_risk_light_task")


# ---------------------------------------------------------------------------------------------------------
# Hand-written JSON-schema subset.
_SCHEMA_KEYWORDS = {"type", "properties", "required", "additionalProperties", "items", "enum", "const",
                    "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "description"}
_TYPES = ("object", "array", "string", "integer", "number", "boolean", "null")


def check_schema(schema: Any, _depth: int = 0) -> None:
    """Raise SchemaError unless schema only uses the supported subset. Unknown keywords are refused, never ignored."""
    if _depth > _MAX_SCHEMA_DEPTH:
        raise SchemaError("schema nested too deeply")
    if not isinstance(schema, dict):
        raise SchemaError("schema must be an object")
    unknown = set(schema) - _SCHEMA_KEYWORDS
    if unknown:
        raise SchemaError(f"unsupported schema keywords {sorted(unknown)}")
    if "type" in schema and schema["type"] not in _TYPES:
        raise SchemaError("unsupported type")
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        raise SchemaError("properties must be an object")
    for sub in props.values():
        check_schema(sub, _depth + 1)
    if "items" in schema:
        check_schema(schema["items"], _depth + 1)
    req = schema.get("required", [])
    if not (isinstance(req, list) and all(isinstance(r, str) for r in req)):
        raise SchemaError("required must be a list of strings")
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        raise SchemaError("additionalProperties must be a boolean")
    if "enum" in schema and not isinstance(schema["enum"], list):
        raise SchemaError("enum must be a list")
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        if key in schema and not (type(schema[key]) is int and schema[key] >= 0):
            raise SchemaError(f"{key} must be a non-negative integer")
    for key in ("minimum", "maximum"):
        if key in schema and type(schema[key]) not in (int, float):
            raise SchemaError(f"{key} must be a number")


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in (int, float) and value == value and abs(value) != float("inf")
    if expected == "boolean":
        return type(value) is bool
    return value is None


def validate_instance(value: Any, schema: dict, path: str = "$", _depth: int = 0) -> list[str]:
    """Return error codes like '$.label:type'. Codes never contain the offending value."""
    errs: list[str] = []
    if _depth > _MAX_SCHEMA_DEPTH:
        return [f"{path}:too_deep"]
    if "type" in schema and not _type_ok(value, schema["type"]):
        return [f"{path}:type"]
    if "const" in schema and (value != schema["const"] or type(value) is not type(schema["const"])):
        errs.append(f"{path}:const")
    if "enum" in schema and not any(value == e and type(value) is type(e) for e in schema["enum"]):
        errs.append(f"{path}:enum")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{path}:minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{path}:maxLength")
    if type(value) in (int, float):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}:minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}:maximum")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"{path}:minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}:maxItems")
        if "items" in schema:
            for i, item in enumerate(value):
                errs.extend(validate_instance(item, schema["items"], f"{path}[{i}]", _depth + 1))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errs.append(f"{path}.{req}:required")
        for k, v in value.items():
            if k in props:
                errs.extend(validate_instance(v, props[k], f"{path}.{k}", _depth + 1))
            elif schema.get("additionalProperties", True) is False:
                errs.append(f"{path}:additional_property")
    return errs


def _strings(max_len: int = 4000) -> dict:
    return {"type": "string", "maxLength": max_len}


DEFAULT_OUTPUT_SCHEMAS: dict[str, dict] = {
    "classification": {"type": "object", "additionalProperties": False, "required": ["label"], "properties": {
        "label": {"type": "string", "minLength": 1, "maxLength": 64},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}}},
    "summarisation": {"type": "object", "additionalProperties": False, "required": ["summary"], "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 4000}}},
    "extraction": {"type": "object", "additionalProperties": False, "required": ["fields"], "properties": {
        "fields": {"type": "object"}}},
    "policy_proposal": {"type": "object", "additionalProperties": False, "required": ["proposal", "rationale"],
                        "properties": {"proposal": {"type": "object"}, "rationale": _strings()}},
}
_ASSESSMENT = {"type": "object", "additionalProperties": False, "required": ["assessment", "needs_human"],
               "properties": {"assessment": _strings(), "findings": {"type": "array", "maxItems": 50, "items": _strings(500)},
                              "needs_human": {"type": "boolean"}}}
for _t in ("investigation", "ambiguous_evidence", "contradictory_tool_results"):
    DEFAULT_OUTPUT_SCHEMAS[_t] = copy.deepcopy(_ASSESSMENT)
_TOOL_CALL_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["tool", "args"],
                     "properties": {"tool": {"type": "string"}, "args": {"type": "object"}}}


# ---------------------------------------------------------------------------------------------------------
# Circuit breaker and endpoint registry.
class CircuitBreaker:
    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(self, failure_threshold: int = 3, cooldown_s: float = 30.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if type(failure_threshold) is not int or failure_threshold < 1:
            raise ValueError("failure_threshold must be a positive integer")
        if cooldown_s < 0:
            raise ValueError("cooldown_s must be non-negative")
        self.failure_threshold, self.cooldown_s, self._clock = failure_threshold, float(cooldown_s), clock
        self._lock = threading.Lock()
        self._state = self.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._probe_in_flight = False

    def _refresh(self) -> None:
        if self._state == self.OPEN and self._clock() - self._opened_at >= self.cooldown_s:
            self._state, self._probe_in_flight = self.HALF_OPEN, False

    @property
    def state(self) -> str:
        with self._lock:
            self._refresh()
            return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    def available(self) -> bool:
        """Would a call be admitted now? Does not reserve the half-open probe."""
        with self._lock:
            self._refresh()
            return self._state == self.CLOSED or (self._state == self.HALF_OPEN and not self._probe_in_flight)

    def acquire(self) -> bool:
        """Admit one call. In half-open exactly one probe is admitted until its result is recorded."""
        with self._lock:
            self._refresh()
            if self._state == self.CLOSED:
                return True
            if self._state == self.HALF_OPEN and not self._probe_in_flight:
                self._probe_in_flight = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state, self._failures, self._probe_in_flight = self.CLOSED, 0, False

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state == self.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state, self._opened_at, self._probe_in_flight = self.OPEN, self._clock(), False


_STATUSES = ("enabled", "disabled")


@dataclass
class ModelEndpoint:
    key: str
    model_id: str
    revision: str
    client: Callable[[dict], Any] | None = None
    status: str = "enabled"
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def __post_init__(self) -> None:
        if not (isinstance(self.key, str) and _ID_RE.match(self.key)):
            raise ValueError("endpoint key must be an identifier")
        if not (isinstance(self.model_id, str) and self.model_id):
            raise ValueError("model_id is required")
        if not (isinstance(self.revision, str) and _REV_RE.match(self.revision)):
            raise ValueError("revision must be a pinned 40-hex commit id")
        if self.status not in _STATUSES:
            raise ValueError(f"status must be one of {_STATUSES}")

    def is_available(self) -> bool:
        return self.status == "enabled" and self.client is not None and self.breaker.available()

    def describe(self) -> dict[str, Any]:
        return {"key": self.key, "model_id": self.model_id, "revision": self.revision}


class ModelRegistry:
    def __init__(self) -> None:
        self._endpoints: dict[str, ModelEndpoint] = {}

    def register(self, endpoint: ModelEndpoint) -> ModelEndpoint:
        if endpoint.key in self._endpoints:
            raise ValueError(f"endpoint {endpoint.key!r} already registered")
        self._endpoints[endpoint.key] = endpoint
        return endpoint

    def get(self, key: str) -> ModelEndpoint:
        return self._endpoints[key]

    def set_status(self, key: str, status: str) -> None:
        if status not in _STATUSES:
            raise ValueError(f"status must be one of {_STATUSES}")
        self._endpoints[key].status = status

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {k: {**e.describe(), "status": e.status, "breaker": e.breaker.state,
                    "consecutive_failures": e.breaker.consecutive_failures} for k, e in self._endpoints.items()}


def default_registry(nano_client: Callable[[dict], Any] | None = None,
                     lightning_client: Callable[[dict], Any] | None = None,
                     clock: Callable[[], float] = time.monotonic,
                     failure_threshold: int = 3, cooldown_s: float = 30.0) -> ModelRegistry:
    reg = ModelRegistry()
    reg.register(ModelEndpoint(NANO_KEY, NANO_MODEL_ID, NANO_REVISION, nano_client,
                               breaker=CircuitBreaker(failure_threshold, cooldown_s, clock)))
    reg.register(ModelEndpoint(LIGHTNING_KEY, LIGHTNING_MODEL_ID, LIGHTNING_REVISION, lightning_client,
                               breaker=CircuitBreaker(failure_threshold, cooldown_s, clock)))
    return reg


# ---------------------------------------------------------------------------------------------------------
# Reply parsing.
def _reject_constant(name: str) -> Any:
    raise ValueError("non-finite number")


def _no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate key")
        out[k] = v
    return out


def _parse_reply(raw: Any) -> tuple[Any, str]:
    """Return (parsed object, '') or (None, error_code). Never repairs: no fence stripping, no coercion."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return None, "invalid_json"
    if isinstance(raw, str):
        if len(raw) > MAX_REPLY_CHARS:
            return None, "reply_too_large"
        try:
            return json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_no_dupes), ""
        except (ValueError, RecursionError):
            return None, "invalid_json"
    if isinstance(raw, dict):
        try:
            return json.loads(_canonical(raw)), ""
        except (TypeError, ValueError, RecursionError):
            return None, "invalid_json"
    return None, "invalid_json"


@dataclass(frozen=True)
class RouteResult:
    decision: str
    output: dict | None
    record: dict


# ---------------------------------------------------------------------------------------------------------
class DecisionRouter:
    def __init__(self, registry: ModelRegistry, clock: Callable[[], float] = time.monotonic,
                 policy_version: str = "router-policy-v1", prompt_template_version: str = "prompt-template-v1",
                 max_retries: int = 1, model_budget_s: float = 30.0,
                 output_schemas: Mapping[str, dict] | None = None,
                 tool_arg_schemas: Mapping[str, dict] | None = None,
                 record_sink: Callable[[dict], None] | None = None, max_records: int = 1000) -> None:
        for name, val in (("policy_version", policy_version), ("prompt_template_version", prompt_template_version)):
            if not (isinstance(val, str) and _ID_RE.match(val)):
                raise ValueError(f"{name} must match [A-Za-z0-9._:-]{{1,64}}")
        if type(max_retries) is not int or not 0 <= max_retries <= 5:
            raise ValueError("max_retries must be an integer in 0..5")
        if model_budget_s <= 0:
            raise ValueError("model_budget_s must be positive")
        for key in (NANO_KEY, LIGHTNING_KEY):
            try:
                registry.get(key)
            except KeyError:
                raise ValueError(f"registry must contain an endpoint named {key!r}") from None
        self.registry, self._clock = registry, clock
        self.policy_version, self.prompt_template_version = policy_version, prompt_template_version
        self.max_retries, self.model_budget_s = max_retries, float(model_budget_s)
        self.schemas = copy.deepcopy(dict(output_schemas)) if output_schemas is not None else copy.deepcopy(DEFAULT_OUTPUT_SCHEMAS)
        for t in TASK_TYPES:
            if t not in self.schemas:
                raise SchemaError(f"no output schema for task_type {t}")
        for sch in self.schemas.values():
            check_schema(sch)
        self.tool_arg_schemas = copy.deepcopy(dict(tool_arg_schemas)) if tool_arg_schemas else {}
        for tool, sch in self.tool_arg_schemas.items():
            check_schema(sch)
            if sch.get("type") != "object" or sch.get("additionalProperties") is not False:
                raise SchemaError(f"tool arg schema for {tool} must be an object with additionalProperties false")
        self.record_sink = record_sink
        self.records: deque[dict] = deque(maxlen=max_records)

    # -- schema for one request ------------------------------------------------------------------------
    def _schema_for(self, meta: RoutingMetadata) -> dict:
        schema = copy.deepcopy(self.schemas[meta.task_type])
        if meta.tool_action is not None:
            schema.setdefault("properties", {})["tool_call"] = copy.deepcopy(_TOOL_CALL_SCHEMA)
        return schema

    def _tool_call_problem(self, reply: dict, meta: RoutingMetadata) -> str:
        if "tool_call" not in reply:
            return ""
        call = reply["tool_call"]
        if meta.tool_action is None:
            return "tool_call_not_requested"
        if call["tool"] != meta.tool_action:
            return "tool_call_wrong_tool"
        schema = self.tool_arg_schemas.get(call["tool"])
        if schema is None:
            return "tool_args_no_schema"
        if validate_instance(call["args"], schema):
            return "tool_args_schema_violation"
        return ""

    # -- one model, bounded attempts -------------------------------------------------------------------
    def _run_model(self, ep: ModelEndpoint, meta: RoutingMetadata, document: str | None,
                   schema: dict, attempts: list[dict]) -> dict | None:
        start = self._clock()
        for _ in range(self.max_retries + 1):
            remaining = self.model_budget_s - (self._clock() - start)
            if remaining <= 0:
                attempts.append({"model": ep.key, "outcome": "budget_exhausted", "latency_ms": 0.0})
                return None
            if not ep.breaker.acquire():
                attempts.append({"model": ep.key, "outcome": "circuit_open", "latency_ms": 0.0})
                return None
            request = {"model_id": ep.model_id, "revision": ep.revision,
                       "prompt_template_version": self.prompt_template_version,
                       "policy_version": self.policy_version, "metadata": meta.as_dict(),
                       "document": document, "document_trust": "untrusted_data_not_instructions",
                       "output_schema": copy.deepcopy(schema), "timeout_s": remaining}
            t0 = self._clock()
            outcome, detail, reply = "ok", "", None
            try:
                raw = ep.client(request)  # type: ignore[misc]  (availability checked by caller)
            except TimeoutError:
                outcome = "timeout"
            except Exception as exc:  # noqa: BLE001  any client failure is a failed attempt; message is dropped
                outcome, detail = "client_error", type(exc).__name__
            else:
                if self._clock() - start > self.model_budget_s:
                    outcome = "timeout"
                else:
                    reply, code = _parse_reply(raw)
                    if code:
                        outcome = code
                    else:
                        errs = validate_instance(reply, schema)
                        if errs:
                            outcome, detail = "schema_violation", errs[0]
                        else:
                            problem = self._tool_call_problem(reply, meta)
                            if problem:
                                outcome = "tool_call_rejected"
                                detail = problem
            row: dict[str, Any] = {"model": ep.key, "outcome": outcome,
                                   "latency_ms": round((self._clock() - t0) * 1000.0, 3)}
            if detail:
                row["detail"] = detail
            attempts.append(row)
            if outcome == "ok":
                ep.breaker.record_success()
                return reply
            ep.breaker.record_failure()
        return None

    # -- public entry ----------------------------------------------------------------------------------
    def route(self, metadata: Any, document: str | None = None) -> RouteResult:
        t0 = self._clock()
        attempts: list[dict] = []
        path: list[str] = []
        try:
            meta = validate_metadata(metadata)
            if document is not None and not isinstance(document, str):
                raise MetadataError("document must be text or None")
        except MetadataError:
            rid = metadata.get("request_id") if isinstance(metadata, Mapping) else None
            rid = rid if isinstance(rid, str) and _ID_RE.match(rid) else None
            return self._finish(DECISION_REJECTED, None, t0, rid, None, None, "rejected", "invalid_metadata",
                                attempts, path, document, None)

        plan = select_route(meta)
        schema = self._schema_for(meta)
        primary = self.registry.get(plan.primary)
        lightning = self.registry.get(LIGHTNING_KEY)

        def attempt(ep: ModelEndpoint) -> dict | None:
            if not ep.is_available():
                attempts.append({"model": ep.key, "outcome": "unavailable", "latency_ms": 0.0})
                path.append(f"{ep.key}:unavailable")
                return None
            out = self._run_model(ep, meta, document, schema, attempts)
            path.append(f"{ep.key}:{'ok' if out is not None else 'failed'}")
            return out

        out = attempt(primary)
        if out is not None:
            return self._finish(DECISION_ANSWERED, out, t0, meta.request_id, meta, plan, "ok", "",
                                attempts, path, document, primary)
        if plan.primary == LIGHTNING_KEY:
            both_down = not self.registry.get(NANO_KEY).is_available() and not lightning.is_available()
            reason = ("both_models_unavailable" if both_down and path[-1].endswith("unavailable")
                      else "lightning_unavailable_for_sensitive_task" if path[-1].endswith("unavailable")
                      else "lightning_failed_for_sensitive_task")
            return self._finish(DECISION_HOLD, None, t0, meta.request_id, meta, plan, "hold", reason,
                                attempts, path, document, None)
        # nano-routed low-risk task whose nano call failed or was unavailable: escalate only if lightning is healthy
        if not lightning.is_available():
            reason = "both_models_unavailable" if path[-1].endswith("unavailable") else "nano_failed_lightning_unavailable"
            return self._finish(DECISION_HOLD, None, t0, meta.request_id, meta, plan, "hold", reason,
                                attempts, path, document, None)
        path.append("escalate_to:lightning")
        out = attempt(lightning)
        if out is not None:
            return self._finish(DECISION_ANSWERED, out, t0, meta.request_id, meta, plan, "ok", "",
                                attempts, path, document, lightning)
        return self._finish(DECISION_HOLD, None, t0, meta.request_id, meta, plan, "hold", "escalation_failed",
                            attempts, path, document, None)

    def _finish(self, decision: str, output: dict | None, t0: float, request_id: str | None,
                meta: RoutingMetadata | None, plan: RoutePlan | None, status: str, reason: str,
                attempts: list[dict], path: list[str], document: str | None,
                selected: ModelEndpoint | None) -> RouteResult:
        primary = self.registry.get(plan.primary) if plan else None
        shown = selected or primary
        calls_per_model: dict[str, int] = {}
        for a in attempts:
            if a["outcome"] not in ("unavailable", "circuit_open", "budget_exhausted"):
                calls_per_model[a["model"]] = calls_per_model.get(a["model"], 0) + 1
        record: dict[str, Any] = {
            "request_id": request_id,
            "decision": decision,
            "status": status,
            "reason": reason,
            "route_reason": plan.reason if plan else "invalid_metadata",
            "primary_model": primary.describe() if primary else None,
            "selected_model": selected.describe() if selected else None,
            "model_id": shown.model_id if shown else None,
            "revision": shown.revision if shown else None,
            "prompt_template_version": self.prompt_template_version,
            "policy_version": self.policy_version,
            "input_sha256": _sha256_text(document if isinstance(document, str) else ""),
            "metadata_sha256": _sha256_text(_canonical(meta.as_dict())) if meta else None,
            "latency_ms": round((self._clock() - t0) * 1000.0, 3),
            "retries": sum(max(0, n - 1) for n in calls_per_model.values()),
            "attempts": attempts,
            "escalation_path": path,
            "escalated": "escalate_to:lightning" in path,
            "fell_back_to_weaker_model": False,
            "authorizes": False,
            "document_used_for_routing": False,
        }
        if output is not None and "tool_call" in output:
            record["proposed_tool"] = output["tool_call"]["tool"]
        tally = [0]
        record = _scrub(record, tally)
        record["redactions"] = tally[0]
        if tally[0] and request_id is not None and record["request_id"] != request_id:
            record["request_id"] = "[REDACTED:request_id]"
        self.records.append(record)
        if self.record_sink is not None:
            try:
                self.record_sink(copy.deepcopy(record))
            except Exception:  # noqa: BLE001  a failing sink must not change the routing outcome
                pass
        return RouteResult(decision, copy.deepcopy(output), copy.deepcopy(record))
