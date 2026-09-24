# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from huf.ai.provider_security import validate_api_base_url

# Brands introduced alongside local network-exposed runtimes (mlx_lm.server,
# laya-serve). Unlike Ollama/LM Studio, these can be started with
# --host 0.0.0.0, which puts an unauthenticated model server on the network.
LOCAL_NETWORK_SERVER_BRANDS = ("mlx", "laya")

_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def requires_auth_for_network_exposed_local_llm(provider_brand, is_local_llm, base_url, api_key):
	"""Return True when a local LLM provider must have a real API key.

	Scoped to `provider_brand in LOCAL_NETWORK_SERVER_BRANDS` only. Ollama and
	LM Studio providers are `is_local_llm=1` and unauthenticated by design;
	every existing row of those brands already carries the "not-needed"
	sentinel, so keying this rule on `is_local_llm` alone would make those
	existing, working providers unsaveable on every future save. mlx/laya did
	not exist before this rule, so no existing row can regress.

	The key is treated as absent when it is empty OR equal to the
	"not-needed" sentinel that `validate_api_key` auto-stamps for keyless
	local providers -- otherwise this check would be dead code, since by the
	time it runs the sentinel has already been written.
	"""
	if (provider_brand or "").strip().lower() not in LOCAL_NETWORK_SERVER_BRANDS:
		return False
	if not is_local_llm:
		return False
	if not base_url:
		return False

	# `url` is a free-form Data field with no scheme validation (only
	# `api_base_url` goes through validate_api_base_url), so a perfectly valid
	# loopback config can arrive as bare "localhost" or "127.0.0.1". urlparse
	# gives no hostname for a scheme-less value, which would fall through to the
	# non-loopback branch and block the commonest local setup. Normalise before
	# parsing so both directions stay correct: "localhost" -> exempt,
	# "192.168.1.50" -> still requires a key.
	raw = base_url.strip()
	if "://" not in raw:
		# A bare IPv6 literal must be bracketed before urlparse can read a
		# hostname out of it ("http://::1" parses to no host, "http://[::1]"
		# parses to "::1"). One colon means host:port, so only bracket when
		# there are several.
		if raw.count(":") > 1 and not raw.startswith("["):
			raw = f"[{raw}]"
		raw = f"http://{raw}"
	candidate = raw
	hostname = (urlparse(candidate).hostname or "").lower()
	if hostname in _LOOPBACK_HOSTS:
		return False

	key_absent = not api_key or api_key == "not-needed"
	return key_absent


class AIProvider(Document):
	def validate(self):
		self.validate_provider_name()
		self.validate_api_key()
		self.validate_api_base_url()
		self.validate_local_network_exposed_api_key()

	def validate_provider_name(self):
		# The provider name becomes the LiteLLM model routing prefix
		# (<provider>/<model>), so it must be a single word.
		if self.provider_name and any(c.isspace() for c in self.provider_name):
			if self.is_new():
				frappe.throw(_("Provider name becomes the model routing prefix — use a single word, e.g. 'Ollama'."))
			else:
				# Existing records keep working via explicit model prefixes;
				# only warn so edits are not blocked.
				frappe.msgprint(
					_("Provider names with spaces cannot be used as a model routing prefix. Use model names with an explicit prefix (e.g. 'ollama_chat/gpt-oss:20b')."),
					indicator="orange",
				)

	def validate_api_key(self):
		if self.is_local_llm:
			if not (self.api_base_url or self.url):
				frappe.throw(_("API Base URL or URL is required for a local LLM provider."))
			if not self.api_key:
				# Local providers (Ollama, LM Studio) need no key; set a dummy
				# value to satisfy legacy readers that expect one.
				self.api_key = "not-needed"
		elif not self.api_key:
			frappe.throw(_("API Key is required for cloud providers."))

	def validate_api_base_url(self):
		# `allow_private` must track `is_local_llm`, exactly as the decision
		# transport already does (huf/ai/decision/transports/systemone_http.py
		# passes `allow_private=bool(is_local_llm)`). Without it a local provider
		# pointed at a LAN address -- e.g. an MLX or Laya server on another
		# machine at http://192.168.1.50:8080 -- is rejected here before it can
		# ever be saved, which is the documented cross-platform deployment shape
		# (a Linux/Docker bench driving MLX on a Mac). Loopback was always
		# allowed either way; this is what makes the LAN case reachable through
		# `api_base_url` rather than only through the unvalidated url+port
		# fields. The network-exposure guard below is what then requires a key.
		validate_api_base_url(self.api_base_url, allow_private=bool(self.is_local_llm))

	def validate_local_network_exposed_api_key(self):
		# Runs after validate_api_key(), which stamps the "not-needed" sentinel
		# onto keyless local providers -- requires_auth_for_network_exposed_local_llm
		# treats that sentinel as an absent key, so running after the stamp
		# (rather than reading a pre-mutation value) is safe and simpler.
		base_url = self.api_base_url or self.url
		if requires_auth_for_network_exposed_local_llm(
			self.provider_brand, self.is_local_llm, base_url, self.api_key
		):
			frappe.throw(
				_(
					"This endpoint is non-loopback and therefore reachable from the network. "
					"Local LLM servers such as mlx_lm.server or laya-serve must be started with "
					"an API key (e.g. --api-key) before they can be used from a non-loopback host."
				)
			)

@frappe.whitelist()
def get_provider_settings(provider_name):
    """
    Finds Single DocTypes that match the pattern '{Provider} % Settings'
    """
    if not provider_name:
        return []

    candidates = frappe.db.sql("""
        SELECT name FROM `tabDocType`
        WHERE issingle = 1
        AND name LIKE %s
        AND name LIKE '%%Settings'
    """, (f"%{provider_name}%",), as_dict=True)

    return [c.name for c in candidates]


@frappe.whitelist()
def get_configured_providers():
    """Return providers that have an API key configured (or are local LLMs).

    Only names and brands are returned; keys are never exposed.
    """
    providers = frappe.get_all(
        "AI Provider",
        fields=["name", "provider_brand", "is_local_llm"],
    )
    result = []
    for p in providers:
        if p.is_local_llm:
            result.append({"name": p.name, "provider_brand": p.provider_brand})
            continue
        try:
            key = frappe.get_doc("AI Provider", p.name).get_password("api_key")
        except Exception:
            key = None
            frappe.log_error(
                message=f"Failed to read API key for AI Provider '{p.name}':\n\n{frappe.get_traceback()}",
                title="AI Provider Key Read Error",
            )
        if key:
            result.append({"name": p.name, "provider_brand": p.provider_brand})
    return result
