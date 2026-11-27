import json
import re

import frappe
import frappe.sessions
from frappe import _
from frappe.utils.telemetry import capture

no_cache = 1

# Flow builder embed mode (docs/flow/BUILDER_EMBED.md, section 2.2).
EMBED_CONFIG_KEY = "huf_embed_frame_ancestors"
_ORIGIN_RE = re.compile(
	r"(?P<scheme>https?)://(?P<host>[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*)(?::(?P<port>[0-9]{1,5}))?",
	re.IGNORECASE | re.ASCII,
)


def _safe_json_embed(data_dict) -> str:
	raw_json = frappe.as_json(data_dict, indent=None, separators=(",", ":"))
	# Escape HTML special characters to unicode escapes so JSON can be safely embedded in HTML templates
	safe_json = raw_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
	return json.dumps(safe_json)


def build_boot_context(extra_boot: dict | None = None) -> dict:
	"""Standard HUF boot context: CSRF token + Guest-branching boot data.

	Extracted from get_context() below so any other renderer that needs the
	same "guest gets get_boot_data(), signed-in user gets sessions.get()"
	boot pattern can reuse it verbatim instead of re-deriving it -- notably
	huf.ai.app_portal_renderer.HufAppPortalRenderer (the per-app www/
	template registry, Phase 2 of the HufAppDeskPortalDelivery track), which
	is explicitly scoped to standardize on this exact pattern rather than
	inventing a second boot mechanism.

	Returns a plain dict with ``build_version``, ``boot`` (safely-embedded
	JSON string) and ``csrf_token`` -- the same three keys get_context()
	updates its context with.
	"""
	csrf_token = frappe.sessions.get_csrf_token()
	# Manually commit the CSRF token here
	frappe.db.commit()  # nosemgrep

	if frappe.session.user == "Guest":
		boot = frappe.website.utils.get_boot_data()
	else:
		try:
			boot = frappe.sessions.get()
		except Exception as e:
			raise frappe.SessionBootFailed from e

	# add server_script_enabled in boot
	if "server_script_enabled" in frappe.conf:
		enabled = frappe.conf.server_script_enabled
	else:
		enabled = True
	boot["server_script_enabled"] = enabled

	if extra_boot:
		boot.update(extra_boot)

	boot_json = _safe_json_embed(boot)

	return {
		"build_version": frappe.utils.get_build_version(),
		"boot": boot_json,
		"csrf_token": csrf_token,
	}


def _normalize_origin(value, allow_http: bool) -> str | None:
	"""``value`` as a browser-style origin (lower case, no default port), or None if it is not an exact origin."""
	if not isinstance(value, str):
		return None
	match = _ORIGIN_RE.fullmatch(value)
	if not match:
		return None
	scheme = match["scheme"].lower()
	if scheme == "http" and not allow_http:
		return None
	origin = f"{scheme}://{match['host'].lower()}"
	if match["port"]:
		port = int(match["port"])
		if not 0 < port <= 65535:
			return None
		if port != (443 if scheme == "https" else 80):
			origin += f":{port}"
	return origin


def get_embed_frame_ancestors() -> list[str]:
	"""Valid entries of the site-config allow-list. Empty means the page may not be framed."""
	configured = frappe.conf.get(EMBED_CONFIG_KEY)
	if not isinstance(configured, list):
		return []
	allow_http = bool(frappe.conf.developer_mode)
	entries = ["'self'" if entry == "'self'" else _normalize_origin(entry, allow_http) for entry in configured]
	return list(dict.fromkeys(entry for entry in entries if entry))


def _site_origin() -> str | None:
	"""The origin the browser used for this request (TLS may end at a proxy)."""
	request = frappe.local.request
	forwarded = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
	return _normalize_origin(f"{forwarded or request.scheme}://{request.host}", allow_http=True)


def _embed_path_segments() -> list[str] | None:
	"""Path segments after ``/huf/embed``, or None when this is not an embed request.

	Empty segments are dropped and the match ignores case, as Frappe's path resolver
	and the client router are at least as lenient.
	"""
	request = getattr(frappe.local, "request", None)
	if not request:
		return None
	segments = [part for part in request.path.strip("/ ").split("/") if part]
	if [part.lower() for part in segments[:2]] != ["huf", "embed"]:
		return None
	return segments[2:]


class EmbedNotPermitted(Exception):
	"""Embed access denied.

	Deliberately not a ``frappe.PermissionError``: Frappe renders those with a Login
	button that would navigate the iframe to /login, which the embed contract forbids
	(docs/flow/BUILDER_EMBED.md). This goes to Frappe's plain error page as a 403.
	"""

	http_status_code = 403

	def __init__(self):
		self.title = _("Not Permitted")
		self.message = _("You do not have access to this flow.")
		super().__init__(self.message)


def _check_embed_access(segments: list[str]) -> None:
	"""Raise EmbedNotPermitted unless the user could open this flow in the full editor."""
	from huf.permissions import has_capability

	allowed = (
		frappe.session.user != "Guest"
		and len(segments) >= 2
		and segments[0].lower() == "flow"
		and has_capability(frappe.session.user, "flows.use")
		and frappe.has_permission("Flow Definition", "read")
	)
	if allowed:
		flow_id = "/".join(segments[1:])
		# A missing flow is left to the editor's "not found" state; it exposes nothing.
		if frappe.db.exists("Flow Definition", flow_id):
			allowed = frappe.has_permission("Flow Definition", "read", doc=flow_id)
	if not allowed:
		raise EmbedNotPermitted()


def _embed_boot(segments: list[str]) -> dict:
	"""Set the frame policy, check access and return the extra boot data for an embed request."""
	ancestors = get_embed_frame_ancestors()
	# Set before the access check so the 403 page carries the same policy.
	frappe.local.response_headers.set(
		"Content-Security-Policy", "frame-ancestors " + (" ".join(ancestors) or "'none'")
	)
	_check_embed_access(segments)
	origins = [_site_origin() if entry == "'self'" else entry for entry in ancestors]
	return {"huf_embed": {"allowed_origins": list(dict.fromkeys(o for o in origins if o))}}


def get_context(context):
	segments = _embed_path_segments()
	extra_boot = None if segments is None else _embed_boot(segments)
	context.update(build_boot_context(extra_boot))
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return json.loads(get_boot())


def get_boot():
	try:
		boot = frappe.sessions.get()
	except Exception as e:
		raise frappe.SessionBootFailed from e

	boot["push_relay_server_url"] = frappe.conf.get("push_relay_server_url")
	return _safe_json_embed(boot)
