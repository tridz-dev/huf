# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Request-time enforcement and revocation for Telegram web-access sessions (see
docs/gateways/telegram-web-access-enforcement.md).

``enforce`` is a ``before_request`` hook. For a normal session it costs one dict lookup
(``session.data.tg_origin``). It deliberately does not import ``telegram_web_access`` at module import
time; the marker contract (``tg_origin``) and path helpers live here as small local copies behind ``_core()``.
"""

import json
import time
from urllib.parse import unquote

import frappe

MARKER_KEY = "tg_origin"
GATEWAY_DOCTYPE = "Gateway"
DENIED_MESSAGE = "Not allowed in a Telegram session"
_CACHE_TTL = 30
_gateway_cache: dict = {}
_binding_cache: dict = {}
_roles_cache: dict = {}
# Roles that are denied by default (kept in step with ``telegram_web_access.PRIVILEGED_ROLES``).
PRIVILEGED_ROLES = frozenset({"System Manager", "Administrator"})
# Request parameters that make Frappe run a (whitelisted) document method.
METHOD_PARAMS = ("run_method", "cmd", "method")

ASSET_PREFIXES = ("/assets", "/files")
LAUNCH_PATH = "/tg_open"  # the launch page must stay reachable: a tap with a live session reuses it
ALWAYS_ALLOWED_METHODS = frozenset(
	{"frappe.ping", "ping", "logout", "web_logout", "huf.ai.telegram_web_access.exchange"}
)

# Verified to exist in Frappe 16 (see docs); names that do not exist were dropped.
DEFAULT_READ_METHODS = frozenset(
	{
		"frappe.desk.query_report.run",
		"frappe.desk.query_report.get_script",
		"frappe.client.get",
		"frappe.client.get_list",
		"frappe.client.get_count",
		"frappe.client.get_value",
		"frappe.desk.reportview.get",
		"frappe.desk.reportview.get_count",
		"frappe.desk.form.load.getdoc",
		"frappe.desk.form.load.getdoctype",
		"frappe.desk.form.load.get_docinfo",
		"frappe.desk.search.search_link",
		"frappe.desk.search.search_widget",
		"frappe.desk.desktop.get_desktop_page",
		"frappe.desk.desk_page.getpage",
		"frappe.desk.notifications.get_notification_info",
		"frappe.apps.get_apps",
	}
)

# Blocked for every Telegram session, writes on or off.
BLOCKED_METHOD_PREFIXES = (
	"frappe.core.doctype.user.user.impersonate",
	"frappe.core.doctype.user.",
	"frappe.core.doctype.user_permission.",
	"frappe.core.doctype.role.",
	"frappe.core.doctype.has_role.",
	"frappe.core.doctype.docperm.",
	"frappe.core.doctype.custom_docperm.",
	"frappe.core.doctype.system_settings.",
	"frappe.core.doctype.server_script.",
	"frappe.core.doctype.data_import.",
	"frappe.core.page.permission_manager.",
	"frappe.core.doctype.rq_job.",
	"frappe.desk.doctype.system_console.",
	"frappe.desk.page.backups.",
	"frappe.permissions.",
	"frappe.utils.bench_manager.",
	"frappe.utils.password.",
	"frappe.installer.",
	"frappe.commands.",
	"frappe.sessions.",
	"frappe.www.login.",
	"frappe.integrations.oauth2.",
)
BLOCKED_DOCTYPES = frozenset(
	{
		"User",
		"Role",
		"Has Role",
		"DocPerm",
		"Custom DocPerm",
		"User Permission",
		"Role Permission for Page and Report",
		"System Settings",
		"Server Script",
		"Client Script",
		"Data Import",
		"System Console",
		"OAuth Client",
		"OAuth Bearer Token",
		"API Key",
		"Session Default Settings",
		"Telegram Admin Binding",
		"Gateway",
		"Role Profile",
		"Custom Role",
		"Module Profile",
		"User Type",
		"User Group",
		"Webhook",
		"Notification",
		"Auto Email Report",
		"Print Format",
		"Custom Field",
		"Property Setter",
		"Customize Form",
		"DocType",
		"Report",
		"Social Login Key",
		"Connected App",
		"Token Cache",
		"Email Account",
		"Email Domain",
		"Access Log",
		"Scheduled Job Type",
		"Console Log",
		"Deleted Document",
	}
)
REPORT_METHODS = frozenset({"frappe.desk.query_report.run", "frappe.desk.query_report.get_script"})
GETDOC_METHOD = "frappe.desk.form.load.getdoc"
UPLOAD_METHODS = frozenset({"upload_file", "frappe.handler.upload_file"})
WRITE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
READ_HTTP = frozenset({"GET", "HEAD"})


# -- local copies of the core contract (replaced by telegram_web_access at merge via _core()) -------------


def _core():
	"""Single accessor for the marker/path helpers. Prefers W21's module, falls back to local copies."""
	try:
		from huf.ai import telegram_web_access as core

		if all(hasattr(core, n) for n in ("session_marker", "normalize_target", "allowed_prefixes")):
			return core
	except Exception:
		pass
	return _LocalCore


class _LocalCore:
	@staticmethod
	def session_marker(session_data):
		marker = (session_data or {}).get(MARKER_KEY) if hasattr(session_data, "get") else None
		return marker if isinstance(marker, dict) else None

	@staticmethod
	def normalize_target(path):
		return normalize_path(path)

	@staticmethod
	def allowed_prefixes(gateway_doc):
		return parse_prefixes(gateway_doc.get("telegram_web_allowed_paths"))


def normalize_path(path) -> str | None:
	"""Return a canonical lower-case absolute path, or None when the input is unsafe (traversal, odd encoding)."""
	if not isinstance(path, str) or not path or "\x00" in path:
		return None
	p = path.split("?", 1)[0].split("#", 1)[0]
	for _i in range(3):
		d = unquote(p)
		if d == p:
			break
		p = d
	else:
		return None
	if "%" in p or "\\" in p or "\x00" in p:
		return None
	segs = []
	for s in p.split("/"):
		if s in ("", "."):
			continue
		if s == ".." or s != s.strip():
			return None
		segs.append(s.lower())
	return "/" + "/".join(segs)


def parse_prefixes(text) -> list[str]:
	out = []
	for line in (text or "").splitlines():
		n = normalize_path(line.strip()) if line.strip() else None
		if n and n != "/":
			for variant in _desk_aliases(n):
				if variant not in out:
					out.append(variant)
	return out


def _desk_aliases(path: str) -> list[str]:
	"""Frappe 16 serves the desk under ``/desk`` and redirects ``/app`` to it: allow both spellings."""
	for here, there in (("/app", "/desk"), ("/desk", "/app")):
		if path == here or path.startswith(here + "/"):
			return [path, there + path[len(here) :]]
	return [path]


def path_allowed(path: str, prefixes) -> bool:
	"""Segment-boundary prefix match on a normalized path."""
	return any(path == p or path.startswith(p + "/") for p in prefixes)


# -- marker / settings ---------------------------------------------------------------------------------


def _current_marker():
	sess = getattr(frappe.local, "session", None)
	data = sess.get("data") if sess else None
	if not data:
		return None
	m = data.get(MARKER_KEY) if hasattr(data, "get") else None
	return m if isinstance(m, dict) else None


def _session_expired() -> bool:
	"""Frappe checks ``session_end`` only when the session comes from the cache; a session reloaded from the
	database after a cache miss would be accepted once more, so the Telegram guard checks it itself."""
	from datetime import UTC, datetime

	data = (getattr(frappe.local, "session", None) or {}).get("data") or {}
	end = data.get("session_end") if hasattr(data, "get") else None
	if not end:
		return False
	try:
		return datetime.now(tz=UTC) > datetime.fromisoformat(str(end))
	except (ValueError, TypeError):
		return True  # unreadable or naive (timezone-less) expiry: fail closed


def _gateway_settings(gateway: str) -> dict:
	now = time.monotonic()
	hit = _gateway_cache.get(gateway)
	if hit and now - hit[0] < _CACHE_TTL:
		return hit[1]
	row = None
	try:
		row = frappe.db.get_value(
			GATEWAY_DOCTYPE,
			gateway,
			[
				"is_enabled",
				"telegram_web_access_enabled",
				"telegram_web_allowed_paths",
				"telegram_web_extra_read_methods",
				"telegram_web_allow_privileged",
			],
			as_dict=True,
		)
	except Exception:
		row = None
	settings = dict(row) if row else {}
	_gateway_cache[gateway] = (now, settings)
	return settings


def clear_gateway_cache():
	_gateway_cache.clear()
	_binding_cache.clear()
	_roles_cache.clear()


def _cached(cache: dict, key, loader):
	now = time.monotonic()
	hit = cache.get(key)
	if hit and now - hit[0] < _CACHE_TTL:
		return hit[1]
	value = loader()
	cache[key] = (now, value)
	return value


def _binding_active(binding: str) -> bool:
	"""True when the binding still exists and is active (cached ~30s)."""

	def load():
		try:
			return bool(frappe.db.get_value("Telegram Admin Binding", binding, "is_active"))
		except Exception:
			return False

	return bool(binding) and _cached(_binding_cache, binding, load)


def _is_privileged(user: str) -> bool:
	def load():
		try:
			return bool(PRIVILEGED_ROLES & set(frappe.get_roles(user)))
		except Exception:
			return True  # cannot tell: treat as privileged (fail closed)

	return _cached(_roles_cache, user, load)


def _revoke_current_session() -> None:
	try:
		sid = frappe.local.session.get("sid") or frappe.session.sid
		if sid:
			frappe.db.delete("Sessions", {"sid": sid})
			frappe.cache.hdel("session", sid)
			frappe.db.commit()
	except Exception:
		pass


# -- decision ------------------------------------------------------------------------------------------


def _doctypes_in(form_dict, *path_doctypes) -> set:
	found = {str(d).lower() for d in path_doctypes if d}
	for key in ("doctype", "dt", "doc", "docs", "doclist", "args"):
		v = form_dict.get(key) if form_dict else None
		if isinstance(v, str):
			if key in ("doctype", "dt"):
				found.add(v.lower())
			else:
				try:
					v = json.loads(v)
				except Exception:
					continue
		for item in v if isinstance(v, list) else [v]:
			if isinstance(item, dict):
				for k in ("doctype", "dt"):
					if isinstance(item.get(k), str):
						found.add(item[k].lower())
	return found


_BLOCKED_DT_LOWER = frozenset(d.lower() for d in BLOCKED_DOCTYPES)


def _report_ok(name) -> bool:
	"""A Report may be run/opened only if it exists and neither it nor the report it derives from is on a
	blocked doctype. Report code runs with the report's own permissions (see docs)."""
	try:
		for _i in range(4):
			if not isinstance(name, str) or not name:
				return False
			row = frappe.db.get_value(
				"Report", name, ["ref_doctype", "report_type", "reference_report"], as_dict=True
			)
			if not row or str(row.get("ref_doctype") or "").lower() in _BLOCKED_DT_LOWER:
				return False
			if row.get("report_type") == "Custom Report" and row.get("reference_report"):
				name = row.get("reference_report")
				continue
			return True
	except Exception:
		pass
	return False


def _extra_methods(settings) -> set:
	return {
		m.strip() for m in (settings.get("telegram_web_extra_read_methods") or "").splitlines() if m.strip()
	}


def decide(marker: dict, settings: dict, method: str, path: str, form_dict) -> bool:
	"""True if the request is allowed. ``path`` is the raw request path."""
	method = (method or "GET").upper()
	form_dict = form_dict or {}
	if "sid" in form_dict:
		return False
	norm = normalize_path(path)
	if norm is None:
		return False
	if not settings or not settings.get("telegram_web_access_enabled") or not settings.get("is_enabled"):
		return False  # missing/unreadable/disabled gateway: closed
	allow_writes = bool(marker.get("allow_writes"))

	# Frappe runs ``form_dict.cmd`` (query string or body) on ANY path, before path routing, so it is
	# resolved first and nothing (assets, resources, navigation) may return early ahead of it.
	form_cmd = form_dict.get("cmd")
	if form_cmd:
		if not isinstance(form_cmd, str):
			return False
		if norm == "/":
			cmd = form_cmd
		elif norm.startswith("/api/method/"):
			raw = normalize_path_keep_case(path)
			path_cmd = raw.split("/method/", 1)[1] if raw and "/method/" in raw else None
			if path_cmd != form_cmd:
				return False  # Frappe would run the ``cmd`` param, not the path method
			cmd = form_cmd
		else:
			return False
		api_method = True
	else:
		cmd = None
		api_method = norm.startswith("/api/method/") or norm.startswith("/api/v2/method/")
		if api_method:
			# method names are case-sensitive; take them from the decoded raw path
			raw = normalize_path_keep_case(path)
			cmd = raw.split("/method/", 1)[1] if raw and "/method/" in raw else None
			if cmd and "/" in cmd:
				# /api/v2/method/<doctype>/<method> is a document method call; /api/method/a/b is not a thing
				return False
			cmd = cmd or None
	if not api_method and norm == LAUNCH_PATH:
		return method in READ_HTTP and not cmd
	if not api_method and (
		norm.startswith(ASSET_PREFIXES[0] + "/") or norm.startswith(ASSET_PREFIXES[1] + "/")
	):
		return method in READ_HTTP
	if api_method:
		if not cmd:
			return False
		if cmd in ALWAYS_ALLOWED_METHODS:
			return True
		if any(cmd == b.rstrip(".") or cmd.startswith(b) for b in BLOCKED_METHOD_PREFIXES):
			return False
		if cmd in REPORT_METHODS:
			if not _report_ok(form_dict.get("report_name")):
				return False
		dts = _doctypes_in(form_dict, norm)
		if cmd == GETDOC_METHOD and _doctypes_in(form_dict) == {"report"}:
			# the report page loads its Report doc (desk query-report view); gate it like run/get_script
			if not _report_ok(form_dict.get("name")):
				return False
		elif dts & _BLOCKED_DT_LOWER:
			return False
		if cmd in UPLOAD_METHODS:
			return allow_writes and method == "POST"
		if cmd in DEFAULT_READ_METHODS or cmd in _extra_methods(settings):
			return True
		return allow_writes and method in READ_HTTP | WRITE_METHODS
	segs = norm.split("/")[1:]  # ["api", "resource", <dt>, <name>] (lower-cased)
	rest = None
	if segs[:2] == ["api", "resource"]:
		rest = segs[2:]
	elif segs[:3] == ["api", "v2", "document"]:
		rest = segs[3:]
	elif segs[:3] == ["api", "v2", "doctype"]:
		if method not in READ_HTTP:
			return False
		rest = segs[3:]
		if len(rest) != 1:
			return False
	if rest is not None:
		# only exact shapes: <dt> or <dt>/<name>; anything deeper (e.g. v2 .../method/<m>) is refused
		if not 1 <= len(rest) <= 2:
			return False
		if _doctypes_in(form_dict, rest[0]) & _BLOCKED_DT_LOWER:
			return False
		if method in READ_HTTP:
			# Frappe's GET handler runs a document method when one of these is present (read permission only)
			if not allow_writes and any(k in form_dict for k in METHOD_PARAMS):
				return False
			return True
		return allow_writes and method in WRITE_METHODS
	if norm.startswith("/api/"):
		return False
	# navigations
	if method not in READ_HTTP:
		return False
	return path_allowed(norm, parse_prefixes(settings.get("telegram_web_allowed_paths")))


def normalize_path_keep_case(path) -> str | None:
	if not isinstance(path, str) or "\x00" in path:
		return None
	p = path.split("?", 1)[0]
	for _i in range(3):
		d = unquote(p)
		if d == p:
			break
		p = d
	if "%" in p or ".." in p.split("/") or "\\" in p:
		return None
	return "/" + "/".join(s for s in p.split("/") if s)


def enforce():
	"""``before_request`` hook. No-op for sessions without a ``tg_origin`` marker."""
	marker = _current_marker()
	if not marker:
		return
	req = getattr(frappe.local, "request", None)
	if req is None:
		return
	try:
		if _session_expired():
			deny()
		settings = _gateway_settings(marker.get("gateway") or "")
		ok = _session_still_valid(marker, settings) and decide(
			marker, settings, req.method, req.path, frappe.local.form_dict
		)
	except _Forbidden:
		raise
	except Exception:
		ok = False
	if not ok:
		deny()


def _session_still_valid(marker: dict, settings: dict) -> bool:
	"""Binding must still be active, and the user must not have newly gained a privileged role."""
	if not _binding_active(marker.get("binding") or ""):
		_revoke_current_session()
		return False
	if not int(settings.get("telegram_web_allow_privileged") or 0) and _is_privileged(frappe.session.user):
		_revoke_current_session()
		return False
	return True


def deny():
	from werkzeug.wrappers import Response

	frappe.local.response = None
	raise _Forbidden(Response(DENIED_MESSAGE, status=403, mimetype="text/plain"))


try:
	from werkzeug.exceptions import Forbidden as _WZForbidden
except Exception:  # pragma: no cover
	_WZForbidden = Exception


class _Forbidden(_WZForbidden):
	code = 403

	def __init__(self, response=None):
		super().__init__(description=DENIED_MESSAGE, response=response)


# -- revocation ----------------------------------------------------------------------------------------


def revoke_binding_sessions(
	binding: str, user: str | None = None, reason: str = "Telegram access revoked"
) -> int:
	"""Delete only the Sessions rows whose data carries ``tg_origin.binding == binding``."""
	if not binding:
		return 0
	if not user:
		user = frappe.db.get_value("Telegram Admin Binding", binding, "frappe_user")
	if not user:
		return 0
	rows = frappe.db.sql(
		"select sid, sessiondata from `tabSessions` where user=%s and sessiondata like %s",
		(user, f"%{MARKER_KEY}%"),
	)
	sids = []
	for sid, raw in rows:
		try:
			data = json.loads(raw or "{}")
		except Exception:
			continue
		m = data.get(MARKER_KEY) if isinstance(data, dict) else None
		if isinstance(m, dict) and m.get("binding") == binding:
			sids.append(sid)
	for sid in sids:
		frappe.db.delete("Sessions", {"sid": sid})
		frappe.cache.hdel("session", sid)
	return len(sids)


def on_binding_update(doc, method=None):
	before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	if before is None:
		return
	deactivated = bool(before.is_active) and not doc.is_active
	changed = any(
		before.get(f) != doc.get(f) for f in ("role_scope", "frappe_user", "telegram_user_id", "gateway")
	)
	if deactivated or changed:
		# the OLD user's rows hold the sessions that were created for this binding
		revoke_binding_sessions(doc.name, before.frappe_user)
		if doc.frappe_user != before.frappe_user:
			revoke_binding_sessions(doc.name, doc.frappe_user)
	_binding_cache.pop(doc.name, None)


def on_binding_trash(doc, method=None):
	revoke_binding_sessions(doc.name, doc.frappe_user)
