# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
AI Provider connection probing — local (Ollama / OpenAI-compatible) and cloud.

Lightweight HTTP probes used to validate provider configuration and to build
capability overrides, so Huf checks what a local model can do instead of
assuming OpenAI-grade behavior.
"""

import frappe
import requests
from frappe import _
from frappe.utils import cint

_PROBE_TIMEOUT = 5
_PROBE_CACHE_TTL = 3600  # 1 hour

# Default endpoints used to sanity-check a cloud provider's API key when the
# record doesn't set its own `api_base_url` override (e.g. Azure/Moonshot/a
# LiteLLM proxy in front of an OpenAI-compatible API).
CLOUD_PROVIDER_ENDPOINTS = {
    "openai": {
        "default_url": "https://api.openai.com/v1/models",
        "list_path": "/models",
        "auth": lambda key: {"Authorization": f"Bearer {key}"},
    },
    "anthropic": {
        "default_url": "https://api.anthropic.com/v1/models",
        "list_path": "/models",
        "auth": lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"},
    },
    "google": {
        "default_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "list_path": "/models",
        # Header-based auth avoids putting the raw API key in the request URL
        # (query params are commonly captured in access/proxy logs).
        "auth": lambda key: {"x-goog-api-key": key},
    },
    "openrouter": {
        "default_url": "https://openrouter.ai/api/v1/auth/key",
        "list_path": "/auth/key",
        "auth": lambda key: {"Authorization": f"Bearer {key}"},
    },
}


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


def probe_cloud_provider(provider_brand: str, api_key: str, api_base_url: str | None = None) -> dict:
    """Verify a cloud provider's API key with a single lightweight call.

    Hits `api_base_url + list_path` when the record overrides the endpoint
    (custom/self-hosted OpenAI-compatible gateways), otherwise the provider's
    public default endpoint. Returns {"ok": bool, "error": str|None}. Never
    raises.
    """
    endpoint = CLOUD_PROVIDER_ENDPOINTS.get(provider_brand)
    if not endpoint:
        return {
            "ok": False,
            "error": f"Test Connection isn't supported for provider brand '{provider_brand}' yet.",
        }
    if not api_key:
        return {"ok": False, "error": "API Key is required for cloud providers."}

    api_base_url = (api_base_url or "").strip()
    url = f"{api_base_url.rstrip('/')}{endpoint['list_path']}" if api_base_url else endpoint["default_url"]

    try:
        resp = requests.get(
            url,
            headers=endpoint["auth"](api_key),
            params=endpoint["params"](api_key) if "params" in endpoint else None,
            timeout=_PROBE_TIMEOUT,
        )
        if resp.status_code in (401, 403):
            return {"ok": False, "error": "API key was rejected by the provider."}
        # Google's Generative Language API returns 400 (not 401/403) for an
        # invalid/expired key, with reason API_KEY_INVALID in the body. Match
        # on that reason specifically — a bare 400 is also how Google reports
        # malformed requests, which are not an auth problem — so the user gets
        # the same clean message instead of a raw HTTPError string.
        if provider_brand == "google" and resp.status_code == 400 and "API_KEY_INVALID" in resp.text:
            return {"ok": False, "error": "API key was rejected by the provider."}
        resp.raise_for_status()
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
def test_provider_connection(
    provider_name: str,
    api_key: str | None = None,
    api_base_url: str | None = None,
    provider_brand: str | None = None,
    is_local_llm=None,
) -> dict:
    """Probe a local provider endpoint and every AI Model linked to it.

    Returns {"provider": {"ok", "error"}, "models": [{"name", "ok",
    "capabilities", "error"}]}. Connection problems are reported in the return
    value — this method never raises to the caller for them.

    The optional arguments let the caller test configuration that hasn't been
    saved yet (the provider form can't read back the stored API key, so a
    freshly typed one would otherwise never be the thing under test). They are
    used for this probe only and are never persisted. Supplying any of them
    requires write access to the provider, since it is equivalent to editing
    the record and then testing it.

    Testing a provider — with or without overrides — makes an outbound,
    credentialed call to the provider's API using stored (or supplied)
    secrets, so the permission check below runs unconditionally, before any
    such call can be made.
    """
    result = {"provider": {"ok": False, "error": None}, "models": []}

    if not frappe.has_permission("AI Provider", "write", provider_name):
        result["provider"]["error"] = _("You do not have permission to test this provider.")
        return result

    try:
        provider_doc = frappe.get_doc("AI Provider", provider_name)
    except Exception as e:
        result["provider"]["error"] = str(e)
        return result

    # An unsaved value wins over the stored one; a blank string means "the user
    # cleared this field", which is distinct from None ("not supplied").
    effective_is_local = (
        cint(is_local_llm) if is_local_llm is not None else provider_doc.get("is_local_llm", 0)
    )
    effective_base_url = (
        api_base_url if api_base_url is not None else provider_doc.get("api_base_url")
    )
    effective_brand = (
        provider_brand if provider_brand else provider_doc.get("provider_brand")
    )

    if not effective_is_local:
        server = probe_cloud_provider(
            effective_brand,
            api_key or provider_doc.get_password("api_key", raise_exception=False),
            effective_base_url,
        )
        result["provider"] = server
        return result

    api_base = (effective_base_url or "").strip() or _resolve_api_base(provider_doc)
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
