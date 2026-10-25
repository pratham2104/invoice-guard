"""Local-inference gate: fail-closed check of an inference config before anything runs.

Hackathon rule: all inference is local, no remote LLM. This module checks a config dict
(and an environment mapping the CALLER passes in; it never reads os.environ itself) and
returns a structured verdict. It is a static config check, not proof that traffic stays
local: it cannot see what a process actually connects to. Pair it with the runtime proof
files that scripts/verify_hackathon.py expects.

Config shape (all optional except that at least one endpoint must be declared):
    {"llm": {"base_url": "http://127.0.0.1:8000/v1", "provider": "vllm", "model": "..."},
     "embedding": {"base_url": ...}, "rerank": {...}, "ocr": {...}, "moderation": {...}}
A flat {"base_url": ..., "provider": ...} also works. The whole structure is scanned
recursively, so an endpoint hidden under an unexpected key is still checked.

Modes
  competition: every violation below rejects.
  prep:        loopback is the only allowed host, so non-loopback URLs still reject (matches
               llm.require_loopback); API keys in the env mapping, hosted/unknown provider
               names and unrecognised *_API_KEY variables are WARNINGS (ok stays True).
  Malformed input rejects in both modes. Any internal error rejects too.

What counts as an endpoint (all checked for loopback, in both modes):
  * any value under a URL-ish key (url, uri, endpoint, host, base, server, address);
  * any string anywhere that is a full URL, starts with "//", or is a schemeless host-like token
    ("api.openai.com", "10.0.0.5:8000/v1", "[2001:db8::1]"), including such tokens or URLs embedded in a
    longer string. File-name-like tokens (model.gguf, config.json) are not host-like;
  * env variables with a URL/URI/ENDPOINT/BASE/SERVER/ADDR/HOST word in the name (except HOSTNAME) such as
    OPENAI_URL or LLM_HOST, and any URL embedded in the value of any env variable;
  * any *PROXY* env variable (HTTP_PROXY, https_proxy, ALL_PROXY...) must be empty or loopback; NO_PROXY is a
    bypass list, not a route, and is ignored.
  "host.openshell.internal" (NemoClaw's sandbox-to-host alias) is NOT loopback here and is rejected like any
  other non-loopback host: this gate has no proof of what that alias resolves to inside a given sandbox. The
  runtime route check (scripts/verify_hackathon.py H03, `nemoclaw inference get`) is where that alias is
  accepted as local.

Result: {"ok": bool, "mode": str, "violations": [{"code","path","detail"}], "warnings": [...],
         "endpoints": [{"path","host","component"}]}. Secret values are never echoed.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

MODES = ("prep", "competition")
MAX_DEPTH, MAX_NODES = 8, 2000

HOSTED_PROVIDER_TOKENS = frozenset({
    "build", "nvidia_build", "nvidiabuild", "openrouter", "openai", "anthropic", "claude", "gemini", "google",
    "vertex", "azure", "bedrock", "cohere", "mistral", "together", "groq", "fireworks", "perplexity",
    "deepseek", "huggingface", "replicate", "xai", "ai21", "cerebras", "sambanova"})
LOCAL_PROVIDERS = frozenset({
    "vllm", "ollama", "llamacpp", "llama.cpp", "lmstudio", "sglang", "tensorrt-llm", "trtllm", "tgi", "local",
    "openai-compatible", "openai_compatible", "openai-compatible-local", "nim-local"})

REMOTE_KEY_NAMES = frozenset({
    "REMOTE_LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "NVIDIA_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "AZURE_OPENAI_API_KEY", "COHERE_API_KEY", "MISTRAL_API_KEY",
    "GROQ_API_KEY", "TOGETHER_API_KEY", "FIREWORKS_API_KEY", "DEEPSEEK_API_KEY", "PERPLEXITY_API_KEY",
    "NGC_API_KEY", "NVAPI_KEY"})
_PROVIDER_KEY_RE = re.compile(
    r"^(REMOTE_LLM|OPENAI|ANTHROPIC|NVIDIA|NGC|GEMINI|GOOGLE|OPENROUTER|AZURE_OPENAI|COHERE|MISTRAL|GROQ|TOGETHER|"
    r"FIREWORKS|DEEPSEEK|PERPLEXITY|XAI|BEDROCK|AWS_BEDROCK)\w*(KEY|TOKEN|SECRET)$")
_GENERIC_KEY_RE = re.compile(r"_API_KEY$")
_ENV_ENDPOINT_RE = re.compile(r"(BASE_URL|API_BASE|API_URL|ENDPOINT|URL|URI)$")
_ENV_ENDPOINT_TOKENS = frozenset({"URL", "URI", "ENDPOINT", "BASE", "SERVER", "ADDR", "ADDRESS", "HOST", "BASEURL",
                                  "APIBASE", "APIURL"})
_ENV_NOT_ENDPOINT = frozenset({"HOSTNAME", "NO_PROXY"})
_URLISH_KEY_RE = re.compile(r"(url|uri|endpoint|host|base|server|address)", re.I)
_FULL_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://\S+$")
_EMBEDDED_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"<>`]+")
_HOSTLIKE_RE = re.compile(
    r"^(?:(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]+)"
    r"|(?:\d{1,3}\.){3}\d{1,3}|\[[0-9a-f:.]+\])(?::\d{1,5})?(?:[/?#]\S*)?$", re.I)
_TOKEN_SPLIT_RE = re.compile(r"[\s,;'\"=`<>|]+")
# Last labels that are file extensions, not top-level domains (".sh", ".py", ".zip" ARE TLDs, so stay checked).
_FILE_EXTS = frozenset({"json", "jsonl", "gguf", "safetensors", "bin", "yaml", "yml", "txt", "onnx", "pth", "log",
                        "toml", "cfg", "conf", "ini", "engine", "plan", "gz", "tar", "pb", "csv", "xml", "html",
                        "ggml", "tflite", "pdf", "png", "jpg"})

_COMPONENTS = (("embed", "embedding"), ("rerank", "rerank"), ("ocr", "ocr"), ("moderat", "moderation"),
               ("guard", "moderation"), ("safety", "moderation"))


class _Malformed(Exception):
    pass


def _component(path: str) -> str:
    low = path.lower()
    for needle, name in _COMPONENTS:
        if needle in low:
            return name
    return "llm"


def is_loopback_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped  # same answer on every Python version
        return ip.is_loopback
    except ValueError:
        return host == "localhost"


def _host_of(value: str) -> tuple[str, str]:
    """(scheme, host). Raises _Malformed for anything that is not a plain, clean URL or host[:port]."""
    if value != value.strip() or not value or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise _Malformed("endpoint contains whitespace or control characters or is empty")
    has_scheme = "://" in value
    parts = urlsplit(value if has_scheme or value.startswith("//") else "//" + value)
    try:
        parts.port  # noqa: B018  raises ValueError on a bad port
    except ValueError as exc:
        raise _Malformed(f"bad port: {exc}") from exc
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise _Malformed("credentials or userinfo in endpoint")
    host = (parts.hostname or "").lower()
    if not host:
        raise _Malformed("endpoint has no host")
    return parts.scheme.lower(), host


def _walk(node: Any, path: str, out: list[tuple[str, str, Any]], budget: list[int], depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise _Malformed("config nested too deeply")
    budget[0] -= 1
    if budget[0] < 0:
        raise _Malformed("config too large")
    if isinstance(node, Mapping):
        for k, v in node.items():
            if not isinstance(k, str):
                raise _Malformed(f"non-string key at {path or '<root>'}")
            _walk(v, f"{path}.{k}" if path else k, out, budget, depth + 1)
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _walk(v, f"{path}[{i}]", out, budget, depth + 1)
    else:
        out.append((path, path.rsplit(".", 1)[-1].split("[")[0], node))


def check_inference_config(config: Any, mode: str, env: Mapping[str, str] | None = None) -> dict:
    """Return {"ok", "mode", "violations", "warnings", "endpoints"}. Never raises; fails closed."""
    violations: list[dict] = []
    warnings: list[dict] = []
    endpoints: list[dict] = []
    strict = mode == "competition"

    def bad(code: str, path: str, detail: str) -> None:
        violations.append({"code": code, "path": path, "detail": detail})

    def soft(code: str, path: str, detail: str) -> None:
        (violations if strict else warnings).append({"code": code, "path": path, "detail": detail})

    try:
        if mode not in MODES:
            bad("invalid_mode", "mode", f"mode must be one of {MODES}")
        elif not isinstance(config, Mapping) or not config:
            bad("malformed_config", "<root>", "config must be a non-empty mapping")
        else:
            leaves: list[tuple[str, str, Any]] = []
            _walk(config, "", leaves, [MAX_NODES])
            env_map: dict[str, Any] = {}
            if env is not None:
                if not isinstance(env, Mapping):
                    raise _Malformed("env must be a mapping")
                env_map.update(env)
            if isinstance(config.get("env"), Mapping):
                env_map.update(config["env"])
            for path, key, value in leaves:
                if path == "env" or path.startswith("env."):
                    continue  # handled below, as environment variables
                low = key.lower()
                if _URLISH_KEY_RE.search(key) or (isinstance(value, str) and _FULL_URL_RE.match(value)):
                    if not isinstance(value, str):
                        bad("malformed_config", path, "endpoint value must be a string")
                        continue
                    _check_endpoint(path, value, bad, endpoints)
                    continue
                if low in ("provider", "vendor", "backend", "api_provider", "service") or low.endswith("_provider"):
                    if not isinstance(value, str) or not value.strip():
                        bad("malformed_config", path, "provider must be a non-empty string")
                    else:
                        _check_provider(path, value, bad, soft)
                if isinstance(value, str):
                    _scan_text(path, value, bad, endpoints, hostlike=True)
            if not endpoints and not violations:
                bad("no_endpoint_declared", "<root>", "config declares no inference endpoint to check")
            for name, value in env_map.items():
                if not isinstance(name, str) or not isinstance(value, (str, type(None))):
                    raise _Malformed("env mapping must be str -> str")
                if not value:
                    continue
                up = name.upper()
                if up in REMOTE_KEY_NAMES or _PROVIDER_KEY_RE.match(up):
                    soft("remote_api_key", f"env.{name}", "remote provider credential present in environment (value not shown)")
                elif _GENERIC_KEY_RE.search(up):
                    warnings.append({"code": "unrecognised_api_key", "path": f"env.{name}",
                                     "detail": "an *_API_KEY variable is set; confirm it is not a remote inference key"})
                elif up in _ENV_NOT_ENDPOINT:
                    pass
                elif "PROXY" in up:
                    _check_endpoint(f"env.{name}", value, bad, endpoints, record=False,
                                    schemes=("", "http", "https", "socks4", "socks4a", "socks5", "socks5h"))
                elif _ENV_ENDPOINT_RE.search(up) or set(re.split(r"[^A-Z0-9]+", up)) & _ENV_ENDPOINT_TOKENS:
                    _check_endpoint(f"env.{name}", value, bad, endpoints)
                else:
                    _scan_text(f"env.{name}", value, bad, endpoints, hostlike=False)
    except _Malformed as exc:
        bad("malformed_config", "<root>", str(exc))
    except Exception as exc:  # noqa: BLE001  fail closed
        bad("gate_error", "<root>", f"{type(exc).__name__}: {exc}")
    return {"ok": not violations, "mode": mode, "violations": violations, "warnings": warnings, "endpoints": endpoints}


def _check_endpoint(path: str, value: str, bad: Any, endpoints: list, record: bool = True,
                    schemes: tuple = ("", "http", "https")) -> None:
    comp = _component(path)
    try:
        scheme, host = _host_of(value)
    except _Malformed as exc:
        bad("malformed_config", path, str(exc))
        return
    if record:
        endpoints.append({"path": path, "host": host, "component": comp})
    if scheme not in schemes:
        bad("bad_scheme", path, f"scheme {scheme!r} not allowed for an inference endpoint")
    elif not is_loopback_host(host):
        bad("remote_endpoint", path, f"{comp} endpoint host {host!r} is not loopback")


def _scan_text(path: str, value: str, bad: Any, endpoints: list, hostlike: bool) -> None:
    """Check URLs (and, when hostlike, schemeless host-like tokens) embedded anywhere in a string."""
    seen: set[str] = set()
    for m in _EMBEDDED_URL_RE.findall(value):
        url = m.rstrip(".,;:)]}")
        seen.add(url)
        _check_endpoint(path, url, bad, endpoints)
    rest = _EMBEDDED_URL_RE.sub(" ", value)
    for tok in _TOKEN_SPLIT_RE.split(rest):
        tok = tok.lstrip("({").rstrip(".,;:)}")
        if tok.startswith("//") and len(tok) > 2:
            _check_endpoint(path, tok, bad, endpoints)
        elif hostlike and tok and _HOSTLIKE_RE.match(tok):
            host = tok.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
            if host.rsplit(".", 1)[-1].lower().split(":")[0] in _FILE_EXTS and "/" not in tok and ":" not in host:
                continue
            _check_endpoint(path, tok, bad, endpoints)


def _check_provider(path: str, value: str, bad: Any, soft: Any) -> None:
    norm = value.strip().lower()
    if norm in LOCAL_PROVIDERS:
        return
    tokens = set(re.split(r"[^a-z0-9_]+", norm)) - {""}
    hosted = sorted(tokens & HOSTED_PROVIDER_TOKENS)
    if hosted:
        soft("hosted_provider", path, f"provider {value!r} names a hosted service ({', '.join(hosted)})")
    else:
        soft("unknown_provider", path, f"provider {value!r} is not a recognised local runtime")
