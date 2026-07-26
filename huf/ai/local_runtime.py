# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Local LLM runtime probing (Ollama / OpenAI-compatible local endpoints).

Lightweight HTTP probes used to validate local provider configuration and to
build capability overrides, so Huf checks what a local model can do instead of
assuming OpenAI-grade behavior.
"""

import frappe
import requests

_PROBE_TIMEOUT = 5
_PROBE_CACHE_TTL = 3600  # 1 hour


def _resolve_api_base(provider_doc) -> str | None:
    """Resolve the API base URL for a local/self-hosted provider.

    Duplicate of huf.ai.providers.litellm._resolve_api_base, kept local so this
    module stays importable without pulling in the LiteLLM provider stack.

    Precedence: `api_base_url` field > `url`+`port` > None.
    """
    if not provider_doc or not provider_doc.get("is_local_llm", 0):
        return None

    api_base = (provider_doc.get("api_base_url") or "").strip()
    if api_base:
        return api_base

    url = (provider_doc.get("url") or "").strip()
    if not url:
        return None

    url = url.rstrip("/")
    port = str(provider_doc.get("port") or "").strip()
    if port and not url.endswith(f":{port}"):
        return f"{url}:{port}"
    return url


def probe_ollama(api_base: str) -> dict:
    """Ping an Ollama server and list its pulled models.

    Returns {"ok": bool, "models": [names], "error": str|None}. Never raises.
    """
    try:
        resp = requests.get(f"{api_base.rstrip('/')}/api/tags", timeout=_PROBE_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return {"ok": True, "models": models, "error": None}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}


def probe_model(api_base: str, model: str) -> dict:
    """Query Ollama for a single model's metadata and capabilities.

    Returns {"ok": bool, "capabilities": [...], "error": str|None}. When the
    model is not pulled, returns ok=False with the server error message.
    Never raises.
    """
    name = model or ""
    for prefix in ("ollama_chat/", "ollama/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    try:
        resp = requests.post(
            f"{api_base.rstrip('/')}/api/show", json={"name": name}, timeout=_PROBE_TIMEOUT
        )
        if resp.status_code != 200:
            try:
                error = resp.json().get("error") or resp.text
            except Exception:
                error = resp.text or f"HTTP {resp.status_code}"
            return {"ok": False, "capabilities": [], "error": str(error)}

        data = resp.json()
        capabilities = data.get("capabilities") or []
        return {"ok": True, "capabilities": capabilities, "error": None}
    except Exception as e:
        return {"ok": False, "capabilities": [], "error": str(e)}


def build_local_overrides(provider_doc, model_name: str) -> dict:
    """Capability overrides for a local provider/model pair.

    Returns {"supports_tools": bool|None, "is_reasoning_model": bool,
    "api_base": str|None}. Probe results are cached in Redis for 1 hour
    (keyed by api_base + model). `supports_tools` is None when the model
    could not be probed (unknown rather than assumed).
    """
    api_base = _resolve_api_base(provider_doc)
    overrides = {"supports_tools": None, "is_reasoning_model": False, "api_base": api_base}
    if not api_base:
        return overrides

    cache_key = f"huf_local_probe|{api_base}|{model_name}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    probe = probe_model(api_base, model_name)
    if probe["ok"]:
        capabilities = probe["capabilities"]
        overrides["supports_tools"] = "tools" in capabilities
        overrides["is_reasoning_model"] = "thinking" in capabilities

    frappe.cache().set_value(cache_key, overrides, expires_in_sec=_PROBE_CACHE_TTL)
    return overrides


@frappe.whitelist()
def test_provider_connection(provider_name: str) -> dict:
    """Probe a local provider endpoint and every AI Model linked to it.

    Returns {"provider": {"ok", "error"}, "models": [{"name", "ok",
    "capabilities", "error"}]}. Connection problems are reported in the return
    value — this method never raises to the caller for them.
    """
    result = {"provider": {"ok": False, "error": None}, "models": []}

    try:
        provider_doc = frappe.get_doc("AI Provider", provider_name)
    except Exception as e:
        result["provider"]["error"] = str(e)
        return result

    api_base = _resolve_api_base(provider_doc)
    if not api_base:
        result["provider"]["error"] = (
            "No API base URL configured — set 'API Base URL' or URL/Port on the provider."
        )
        return result

    server = probe_ollama(api_base)
    result["provider"] = {"ok": server["ok"], "error": server["error"]}

    model_names = frappe.get_all(
        "AI Model", filters={"provider": provider_name}, pluck="model_name"
    )
    for model_name in model_names:
        if not server["ok"]:
            # Server unreachable — every model inherits the connection error
            # instead of paying a per-model timeout.
            result["models"].append(
                {"name": model_name, "ok": False, "capabilities": [], "error": server["error"]}
            )
            continue

        probe = probe_model(api_base, model_name)
        result["models"].append(
            {
                "name": model_name,
                "ok": probe["ok"],
                "capabilities": probe["capabilities"],
                "error": probe["error"],
            }
        )

    return result
