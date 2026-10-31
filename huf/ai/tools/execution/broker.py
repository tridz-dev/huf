"""Broker RPC for sandboxed code (Execution Profile permissions, network policy, doc/report/email ops).

Split out of ``huf.ai.tools.code_execution``, which re-exports ``_make_broker_handler`` and the
network-rule matchers for existing importers.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any
from urllib.parse import urlparse

import frappe

from huf.ai.http_handler import handle_http_request
from huf.ai.tools.functions import get_report_result

# ---------------------------------------------------------------------------
# E4 — Broker RPC (Phase 4a)
#
# Sandboxed code holds no ambient Frappe access. Every side effect round-trips
# over the control socket into the ``broker_handler`` closure built by
# :func:`_make_broker_handler`, which (1) authorizes the call against the
# IMMUTABLE profile snapshot (never the live profile) and the acting user's
# own Frappe permissions, then (2) executes it impersonating ``acting_user``
# captured at dispatch time — never the RQ worker's default user.
#
# Authorization order for every call (fail closed at every step):
#   a. The capability must be known to the broker AND present in the snapshot's
#      ``permissions`` rows.
#   b. For ``doc.*``/``report.run`` the requested doctype (for reports: the
#      report's ``ref_doctype``) must be covered by a granting row — an
#      unscoped row (``reference_doctype`` empty) covers everything; a scoped
#      row covers only its doctype.
#   c. Write capabilities (``doc.create``, ``doc.update``, ``email.send``) are
#      rejected when every applicable row is flagged ``is_read_only``.
#      (Steps b/c are applied to the rows applicable to THIS request, so a
#      read-only-scoped row can never be satisfied by an unrelated writable
#      row on the same capability.)
#   d. For ``doc.*``/``report.run`` the acting user must pass
#      ``frappe.has_permission(doctype, ptype, user=acting_user)``
#      (``read`` for read/get_list/report, ``create`` for create, ``write``
#      for update) — the same two-layer check as
#      ``PermissionAwareToolRegistry._can_use_tool``.
#   e. For ``http.request`` the target host/port/scheme must match a rule of
#      the ``Network Access Policy`` named in the snapshot; no policy ⇒ deny.
#      The request itself goes through
#      ``huf.ai.http_handler.handle_http_request``, which applies the SSRF
#      guard and re-validates every redirect hop.
# ---------------------------------------------------------------------------

#: Document capabilities the broker understands.
_DOC_CAPABILITIES = frozenset({"doc.read", "doc.get_list", "doc.create", "doc.update"})

#: Capabilities rejected when the granting permission row is ``is_read_only``.
_WRITE_CAPABILITIES = frozenset({"doc.create", "doc.update", "email.send"})

#: ``frappe.has_permission`` ptype enforced per document/report capability.
_CAPABILITY_PTYPE = {
	"doc.read": "read",
	"doc.get_list": "read",
	"doc.create": "create",
	"doc.update": "write",
	"report.run": "read",
}

#: Hard cap on rows returned by ``doc.get_list`` regardless of the requested
#: limit, so one call cannot flood the control socket / child memory.
MAX_BROKER_LIST_LIMIT = 500


def _make_broker_handler(profile_snapshot: dict, acting_user: str | None):
	"""Build the ``broker_handler`` closure injected into ``run_sandboxed``.

	The closure authorizes every sandbox broker call against the immutable
	``profile_snapshot`` (never the live profile) and dispatches it
	impersonating ``acting_user``. It NEVER raises: any failure becomes
	``(False, "<ExceptionType>: <msg>")`` so a broker bug cannot crash the
	worker or leak a traceback into sandbox output beyond a summary.

	Authorized calls (denials excluded) are counted per capability on the
	returned closure's ``call_counts`` attribute, which the worker folds into
	the audit record (arguments and results are never counted or stored).
	"""
	permissions = list((profile_snapshot or {}).get("permissions") or [])
	network_policy = (profile_snapshot or {}).get("network_policy") or None
	call_counts: dict[str, int] = {}
	site = frappe.local.site

	def _authorize(capability: Any, params: dict) -> str | None:
		"""Return None when the call may proceed, else a denial reason."""
		if not acting_user:
			return "broker is unavailable (no acting user recorded for this execution)"
		if not isinstance(capability, str) or not capability:
			return "malformed broker request: missing capability"
		if capability not in _DISPATCHERS:
			return f"unknown capability '{capability}'"

		rows = [r for r in permissions if r.get("capability") == capability]
		if not rows:
			return f"capability '{capability}' not granted by profile"

		# (b) Doctype scoping + (d) has_permission for document/report caps.
		# ``email.send``/``http.request`` carry no doctype target; a
		# ``reference_doctype`` set on their rows is ignored by design.
		if capability in _DOC_CAPABILITIES:
			target = params.get("doctype")
			if not isinstance(target, str) or not target:
				return f"{capability} requires a 'doctype' string"
			rows = _scoped_rows(rows, target)
			if not rows:
				return f"capability '{capability}' not granted for doctype '{target}'"
			ptype = _CAPABILITY_PTYPE[capability]
			if not frappe.has_permission(target, ptype, user=acting_user):
				return f"user '{acting_user}' lacks {ptype} permission on '{target}'"
		elif capability == "report.run":
			report_name = params.get("report_name")
			if not isinstance(report_name, str) or not report_name:
				return "report.run requires a 'report_name' string"
			# A missing report raises DoesNotExistError → denial via the wrapper.
			report = frappe.get_doc("Report", report_name)
			ref_doctype = getattr(report, "ref_doctype", None)
			rows = _scoped_rows(rows, ref_doctype)
			if not rows:
				return f"capability 'report.run' not granted for doctype '{ref_doctype}'"
			if not frappe.has_permission("Report", "read", doc=report_name, user=acting_user):
				return f"user '{acting_user}' lacks read permission on Report '{report_name}'"

		# (c) Read-only rows cannot drive writes.
		if capability in _WRITE_CAPABILITIES and all(bool(r.get("is_read_only")) for r in rows):
			return f"capability '{capability}' is granted read-only by this profile"

		# (e) Network policy gate for HTTP egress (runs before the SSRF guard).
		if capability == "http.request":
			return _authorize_egress(params, network_policy)

		return None

	def broker_handler(capability, params):
		"""Wire entrypoint: authorize → count → impersonate → dispatch."""
		try:
			denial = _authorize(capability, params)
			if denial:
				return False, denial
			call_counts[capability] = call_counts.get(capability, 0) + 1
			previous_user = frappe.session.user
			frappe.set_user(acting_user)
			try:
				result = _DISPATCHERS[capability](params)
			finally:
				frappe.set_user(previous_user)
			return True, _json_safe(result)
		except Exception as exc:  # noqa: BLE001 - broker must never crash the worker
			frappe.log_error(title="Huf Code Execution Broker", message=f"broker call {capability!r} failed: {exc}")
			return False, f"{type(exc).__name__}: {exc}"

	def _thread_start():
		"""Establish frappe context for the broker's own OS thread.

		``broker_handler`` runs on the daemon thread spawned by
		``run_sandboxed`` for the lifetime of one execution, not on the RQ
		job's main thread. ``frappe.local`` is a ``werkzeug.local.Local``
		keyed by OS thread identity, so that thread starts with no
		site/db/session context of its own — every frappe.* call inside
		``broker_handler`` (has_permission, get_doc, set_user, log_error)
		would otherwise fail. Called once by the thread before it services
		any request.
		"""
		frappe.init(site=site)
		frappe.connect()

	def _thread_end():
		"""Tear down the broker thread's frappe context (closes its DB connection)."""
		frappe.destroy()

	broker_handler.call_counts = call_counts
	broker_handler.thread_start = _thread_start
	broker_handler.thread_end = _thread_end
	return broker_handler


def _scoped_rows(rows: list, target_doctype: str | None) -> list:
	"""Keep permission rows whose scope covers ``target_doctype``.

	An unscoped row (no ``reference_doctype``) covers every doctype; a scoped
	row covers only its exact doctype.
	"""
	return [
		row
		for row in rows
		if not row.get("reference_doctype") or row.get("reference_doctype") == target_doctype
	]


def _authorize_egress(params: dict, network_policy: str | None) -> str | None:
	"""Network-policy gate for ``http.request`` (runs before the SSRF guard).

	Returns None when the target is permitted by the policy named in the
	snapshot, else a denial reason. Fails closed: no policy on the profile, an
	unparseable URL, a missing policy document, or no matching rule all deny.
	"""
	if not network_policy:
		return "http.request denied: the profile names no network policy (egress disabled)"

	url = params.get("url")
	if not isinstance(url, str) or not url:
		return "http.request requires a 'url' string"

	parsed = urlparse(url)
	scheme = (parsed.scheme or "").lower()
	if scheme not in ("http", "https"):
		return f"http.request denied: scheme '{parsed.scheme or '(none)'}' is not allowed"
	if not parsed.hostname:
		return "http.request denied: URL has no hostname"
	try:
		port = parsed.port or (443 if scheme == "https" else 80)
	except ValueError:
		return "http.request denied: invalid port in URL"

	try:
		policy = frappe.get_doc("Network Access Policy", network_policy)
	except Exception:
		return f"http.request denied: network policy '{network_policy}' not found"

	for rule in policy.rules or []:
		if not _rule_host_matches(rule.host_or_cidr, parsed.hostname):
			continue
		if not _rule_port_matches(rule.port_range, port):
			continue
		protocol = (rule.protocol or "").strip().lower()
		if protocol and protocol != scheme:
			continue
		return None

	return (
		f"http.request denied: {scheme}://{parsed.hostname}:{port} "
		f"is not allowed by network policy '{network_policy}'"
	)


def _rule_host_matches(host_or_cidr: str | None, host: str) -> bool:
	"""Match a rule's ``host_or_cidr`` against the request host.

	Exact case-insensitive hostname match, or — when the rule parses as an IP
	network — containment of a request host that is itself an IP literal. No
	DNS resolution happens here (the SSRF guard resolves separately), so a
	CIDR rule never matches a hostname, and a hostname rule never matches an
	IP. No wildcard/subdomain matching in v1.
	"""
	spec = (host_or_cidr or "").strip()
	if not spec or not host:
		return False
	try:
		network = ipaddress.ip_network(spec, strict=False)
	except ValueError:
		network = None
	if network is not None:
		try:
			address = ipaddress.ip_address(host)
		except ValueError:
			return False
		return address in network
	return host.lower() == spec.lower()


def _rule_port_matches(port_range: str | None, port: int) -> bool:
	"""Match a rule's ``port_range`` (``"80"``, ``"8000-9000"``, comma lists).

	An empty spec imposes no port constraint. An unparseable spec matches
	nothing (fail closed).
	"""
	spec = (port_range or "").strip()
	if not spec:
		return True
	for part in spec.split(","):
		part = part.strip()
		if not part:
			continue
		lo, sep, hi = part.partition("-")
		try:
			if sep:
				if int(lo) <= port <= int(hi):
					return True
			elif int(part) == port:
				return True
		except ValueError:
			continue
	return False


def _require_str(params: dict, key: str, capability: str) -> str:
	"""Fetch a non-empty string param or raise a clear ``ValueError``."""
	value = params.get(key)
	if not isinstance(value, str) or not value:
		raise ValueError(f"{capability} requires a '{key}' string")
	return value


def _validate_str_list(value: Any, key: str, capability: str) -> list | None:
	"""Validate an optional list-of-strings param (``fields``)."""
	if value is None:
		return None
	if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
		raise ValueError(f"{capability} '{key}' must be a list of strings")
	return value


def _validate_limit(value: Any, capability: str) -> int | None:
	"""Validate an optional integer ``limit`` param."""
	if value is None:
		return None
	if isinstance(value, bool) or not isinstance(value, int | float | str):
		raise ValueError(f"{capability} 'limit' must be an integer")
	try:
		return int(value)
	except (TypeError, ValueError):
		raise ValueError(f"{capability} 'limit' must be an integer") from None


def _op_doc_read(params: dict) -> dict:
	doctype = _require_str(params, "doctype", "doc.read")
	name = _require_str(params, "name", "doc.read")
	fields = _validate_str_list(params.get("fields"), "fields", "doc.read")
	doc = frappe.get_doc(doctype, name)
	data = doc.as_dict()
	if fields:
		keep = set(fields)
		data = {key: value for key, value in data.items() if key in keep}
	return data


def _op_doc_get_list(params: dict) -> list:
	doctype = _require_str(params, "doctype", "doc.get_list")
	filters = params.get("filters")
	if filters is not None and not isinstance(filters, dict | list):
		raise ValueError("doc.get_list 'filters' must be a dict or list")
	fields = _validate_str_list(params.get("fields"), "fields", "doc.get_list")
	limit = _validate_limit(params.get("limit"), "doc.get_list")
	# ``frappe.get_list`` (not ``get_all``) is deliberate: running under the
	# impersonated acting user, it applies that user's record-level
	# permissions (permission query conditions) on top of the doctype check.
	return frappe.get_list(
		doctype,
		filters=filters or None,
		fields=fields or None,
		limit_page_length=min(limit or 20, MAX_BROKER_LIST_LIMIT),
	)


def _op_doc_create(params: dict) -> dict:
	doctype = _require_str(params, "doctype", "doc.create")
	values = params.get("values")
	if not isinstance(values, dict):
		raise ValueError("doc.create 'values' must be a dict of field values")
	# The authorized target is ``doctype`` from ``params`` (checked by
	# ``_authorize`` against the profile snapshot). ``values`` is fully
	# sandbox-controlled, so a smuggled "doctype" key inside it must never
	# override the authorized target — doctype is applied last, deliberately.
	doc = frappe.get_doc({**values, "doctype": doctype})
	doc.insert()
	return {"doctype": doctype, "name": doc.name}


def _op_doc_update(params: dict) -> dict:
	doctype = _require_str(params, "doctype", "doc.update")
	name = _require_str(params, "name", "doc.update")
	values = params.get("values")
	if not isinstance(values, dict):
		raise ValueError("doc.update 'values' must be a dict of field values")
	# Strip any attacker-supplied doctype/name from values so the update
	# can never retarget a different, unauthorized document.
	safe_values = {k: v for k, v in values.items() if k not in ("doctype", "name")}
	doc = frappe.get_doc(doctype, name)
	doc.update(safe_values)
	doc.save()
	return {"doctype": doctype, "name": doc.name}


def _op_email_send(params: dict) -> dict:
	recipients = params.get("recipients")
	if isinstance(recipients, str):
		recipients = [recipients]
	if (
		not isinstance(recipients, list)
		or not recipients
		or not all(isinstance(r, str) and r for r in recipients)
	):
		raise ValueError("email.send 'recipients' must be a non-empty list of addresses")
	subject = _require_str(params, "subject", "email.send")
	message = _require_str(params, "message", "email.send")
	frappe.sendmail(recipients=recipients, subject=subject, message=message)
	return {"queued": True, "recipients": recipients}


def _op_http_request(params: dict) -> dict:
	method = _require_str(params, "method", "http.request").upper()
	url = _require_str(params, "url", "http.request")
	# The network-policy gate already ran in authorization; ``handle_http_request``
	# applies the SSRF guard to the URL and re-validates every redirect hop.
	# NOTE (known v1 limitation): redirect hops are SSRF-checked but NOT
	# re-checked against the Network Access Policy — a redirect can egress to a
	# host outside the policy. Flagged for Phase 4b/5 hardening rather than
	# hand-rolling a redirect loop here (the SSRF helper must stay the single
	# owner of HTTP egress).
	return handle_http_request(
		method,
		url,
		headers=params.get("headers"),
		params=params.get("params"),
		data=params.get("data"),
		json_data=params.get("json_data"),
	)


def _op_report_run(params: dict) -> dict:
	report_name = _require_str(params, "report_name", "report.run")
	filters = params.get("filters")
	if filters is not None and not isinstance(filters, dict):
		raise ValueError("report.run 'filters' must be a dict")
	limit = _validate_limit(params.get("limit"), "report.run")
	# Dispatch runs under ``frappe.set_user(acting_user)``, so
	# ``frappe.session.user`` IS the acting user here; the codebase's report
	# runner forwards it so user-level permissions apply to the report data.
	return get_report_result(
		report_name, filters=filters, limit=limit, user=frappe.session.user
	)


_DISPATCHERS = {
	"doc.read": _op_doc_read,
	"doc.get_list": _op_doc_get_list,
	"doc.create": _op_doc_create,
	"doc.update": _op_doc_update,
	"email.send": _op_email_send,
	"http.request": _op_http_request,
	"report.run": _op_report_run,
}


def _json_safe(value: Any) -> Any:
	"""Round-trip a broker result through JSON so it is always wire-serializable.

	Frappe values such as ``datetime`` are stringified (``default=str``),
	matching how Frappe's own JSON responses serialize them.
	"""
	return json.loads(json.dumps(value, default=str))
