"""Python code execution tool — dispatcher, RQ enqueue, and worker (Phase 3).

This module is the ``function_path`` target for an ``Agent Tool Function`` of
type ``Code Execution`` (mirroring the other ``App Provided`` tools in
``huf/ai/tools/_registry.py``). The LLM-facing entrypoint is :func:`run_python`.

Flow:
  1. :func:`run_python` validates the site/agent/profile gates, snapshots the
     Execution Profile, creates an ``Agent Tool Call`` audit record, and either
     enqueues execution (Auto Approve), parks it behind an
     ``Agent Execution Approval`` record (Ask Every Time), or rejects it
     (Never Allow).
  2. :func:`enqueue_execution` submits :func:`execute_job` to the dedicated
     ``code-execution`` RQ queue.
  3. :func:`execute_job` (the RQ worker) subprocess-launches the isolated
     interpreter via :func:`huf.ai.tools.execution_sandbox.run_sandboxed` and
     writes the measured outcome back onto the ``Agent Tool Call``.

The actual isolation boundary lives in ``execution_sandbox.py`` (which is
frappe-free). This module is the only place that touches Frappe state.

Running a worker for the queue (operator note)::

    bench --site <site> worker --queue code-execution

``huf/hooks.py`` does not need to declare the queue — ``frappe.enqueue(...,
queue="code-execution")`` is sufficient as long as a worker listens on it.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import shutil
import tempfile
from typing import Any
from urllib.parse import urlparse

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.http_handler import handle_http_request
from huf.ai.tool_functions import get_report_result
from huf.ai.tools.execution_sandbox import (
	DEFAULT_MAX_OUTPUT_BYTES,
	DEFAULT_WALL_TIME_S,
	RQ_WALL_GRACE_S,
	ExecutionResult,
	run_sandboxed,
)
from huf.permissions import has_capability

#: Tool name recorded on the audit record when the caller does not supply one.
_TOOL_NAME = "run_python"

#: How long an ``Ask Every Time`` approval stays valid before expiring.
_APPROVAL_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _is_site_enabled() -> bool:
	"""Read the site kill switch ``huf_python_execution_enabled`` (default off)."""
	val = frappe.conf.get("huf_python_execution_enabled")
	if isinstance(val, bool):
		return val
	if val is None:
		return False
	if isinstance(val, (int, float)):
		return bool(val)
	return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _name_of(obj: Any) -> str | None:
	"""Return the Frappe document name for a doc-or-name argument (or None)."""
	if obj is None:
		return None
	return getattr(obj, "name", None) or str(obj)


def _as_agent_doc(agent_doc: Any) -> Any:
	"""Resolve ``agent_doc`` (Document or name) to an ``Agent`` document."""
	if hasattr(agent_doc, "doctype"):
		return agent_doc
	return frappe.get_doc("Agent", agent_doc)


def _sha256(code: str) -> str:
	return hashlib.sha256((code or "").encode("utf-8")).hexdigest()


def _parse_json_field(value: Any, default):
	"""Normalize a Frappe JSON field that may arrive as dict/list or string."""
	if value is None or value == "":
		return default
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except (TypeError, ValueError):
		return default


def _build_profile_snapshot(profile) -> dict:
	"""Build an immutable, JSON-serializable snapshot of an Execution Profile.

	Stored verbatim on the ``Agent Tool Call`` so later edits to the profile do
	not retroactively change the audit meaning of a past call.
	"""
	permissions = []
	for row in profile.permissions or []:
		permissions.append(
			{
				"capability": row.capability,
				"reference_doctype": row.reference_doctype or None,
				"is_read_only": bool(row.is_read_only),
			}
		)

	return {
		"profile_name": profile.profile_name,
		"is_builtin": bool(profile.is_builtin),
		"approval_mode": profile.approval_mode,
		"filesystem_policy": profile.filesystem_policy,
		"network_policy": profile.network_policy or None,
		"allowed_modules": _parse_json_field(profile.allowed_modules, []),
		"permissions": permissions,
		"limits": {
			"max_wall_time_s": int(profile.max_wall_time_s or 0),
			"max_cpu_seconds": int(profile.max_cpu_seconds or 0),
			"max_memory_mb": int(profile.max_memory_mb or 0),
			"max_output_bytes": int(profile.max_output_bytes or 0),
		},
	}


def _capability_summary(profile) -> str:
	"""Comma-joined broker capabilities granted by the profile (for approvals)."""
	caps = [r.capability for r in (profile.permissions or []) if r.capability]
	return ", ".join(caps) if caps else "code_execution.run"


def _truncate(text: str | None, limit: int) -> str | None:
	if text is None:
		return None
	if len(text) <= limit:
		return text
	return text[:limit] + f"\n... [truncated; {len(text) - limit} chars omitted]"


# ---------------------------------------------------------------------------
# E1 — Dispatcher (LLM-facing tool entrypoint)
# ---------------------------------------------------------------------------


def run_python(
	code: str,
	agent_doc: Any,
	conversation: Any = None,
	agent_run: Any = None,
	**kwargs: Any,
) -> dict:
	"""Dispatch a Python code execution request from an agent.

	Args:
		code: The Python source to execute. Never persisted on the audit
			record; only its SHA-256 (``code_ref``) is stored.
		agent_doc: The ``Agent`` document (or its name) invoking the tool.
		conversation: The ``Agent Conversation`` doc/name (for audit linkage).
		agent_run: The ``Agent Run`` doc/name (for audit linkage).
		**kwargs: May carry ``call_id``/``tool_call_id``/``tool_name`` from the
			tool framework.

	Returns:
		A JSON-serializable dict describing the dispatched/parked call.

	Raises:
		frappe.ValidationError: kill switch off / agent not enabled / profile
			disabled.
		frappe.PermissionError: user lacks ``code_execution.run`` or the
			profile policy is ``Never Allow``.
	"""
	# 1. Site kill switch (checked before any DB lookup, mirroring
	#    Frappe's ``server_script_enabled`` gate).
	if not _is_site_enabled():
		frappe.throw(
			"Python code execution is disabled on this site.",
			frappe.ValidationError,
		)

	# The user driving this request. Captured NOW and threaded to the RQ
	# worker, because the worker runs as a privileged/system user and every
	# broker call must impersonate the original requester instead.
	acting_user = frappe.session.user

	# 2. Per-user capability (defense-in-depth; also enforced at tool-offer
	#    time in ``tool_registry.PermissionAwareToolRegistry``).
	if not has_capability(acting_user, "code_execution.run"):
		frappe.throw(
			"You do not have permission to run Python code.",
			frappe.PermissionError,
		)

	# 3. Per-agent enable + profile.
	agent = _as_agent_doc(agent_doc)
	if not getattr(agent, "allow_code_execution", None) or not getattr(
		agent, "execution_profile", None
	):
		frappe.throw(
			"Code execution is not enabled for this agent.",
			frappe.ValidationError,
		)

	# 4. Profile must be enabled.
	profile = frappe.get_doc("Execution Profile", agent.execution_profile)
	if profile.disabled:
		frappe.throw(
			"The selected Execution Profile is disabled.",
			frappe.ValidationError,
		)

	# 5/6. Snapshot + code hash (raw code is never stored on the audit row).
	snapshot = _build_profile_snapshot(profile)
	code_ref = _sha256(code)

	# 7. Create the audit record (Started). ``tool_args`` references the hash,
	#    never the raw code. ``ignore_permissions`` is used because the audit
	#    row is created by the trusted dispatcher on behalf of the acting user,
	#    who is not expected to hold write perm on ``Agent Tool Call``.
	call = frappe.get_doc(
		{
			"doctype": "Agent Tool Call",
			"agent_run": _name_of(agent_run),
			"conversation": _name_of(conversation),
			"tool": kwargs.get("tool_name") or _TOOL_NAME,
			"is_mcp_tool": 0,
			"tool_args": json.dumps({"code_ref": code_ref}),
			"status": "Started",
			"call_id": kwargs.get("call_id") or kwargs.get("tool_call_id"),
			"execution_profile": profile.name,
			"execution_profile_snapshot": snapshot,
			"code_ref": code_ref,
		}
	)
	call.insert(ignore_permissions=True)

	approval_mode = profile.approval_mode

	# 8a. Never Allow — hard deny, no enqueue.
	if approval_mode == "Never Allow":
		call.status = "Failed"
		call.error_message = "Execution not permitted by profile policy."
		call.save(ignore_permissions=True)
		frappe.throw(
			"Execution not permitted by profile policy.",
			frappe.PermissionError,
		)

	# 8b. Ask Every Time — park behind an approval record, do NOT enqueue.
	if approval_mode == "Ask Every Time":
		# ``ignore_permissions=True`` is intentional and security-relevant: the
		# dispatcher is a trusted internal path that has already enforced the
		# kill switch + ``code_execution.run`` capability + agent/profile gates,
		# and the requesting user is not expected to hold the
		# ``execution.approve`` capability that
		# ``Agent Execution Approval.has_permission`` requires for manual create.
		# Recording a decision on that record still requires
		# ``execution.approve`` / a designated approver (see ``_can_decide``), so
		# the user who triggered execution cannot self-approve.
		approval = frappe.get_doc(
			{
				"doctype": "Agent Execution Approval",
				"agent_tool_call": call.name,
				"requested_capability": _capability_summary(profile),
				"code_ref": code_ref,
				"status": "Pending",
				"expires_on": add_to_date(now_datetime(), hours=_APPROVAL_TTL_HOURS),
			}
		)
		approval.insert(ignore_permissions=True)

		# ``Agent Tool Call.status`` has no dedicated "waiting" option; "Queued"
		# is the closest available value, and the linked
		# ``Agent Execution Approval.status == "Pending"`` is the real
		# waiting-state signal. (Open question for review: add an explicit
		# "Waiting Approval" status in a later phase.)
		call.status = "Queued"
		call.save(ignore_permissions=True)

		# TODO(phase5): when ``approve_execution()`` transitions the approval to
		# "Approved" (huf.huf.doctype.agent_execution_approval...), the
		# resolution path must call
		# ``huf.ai.tools.code_execution.enqueue_execution(call.name, code, snapshot, acting_user=...)``
		# to finally dispatch the RQ job. The raw ``code`` is NOT persisted on
		# the ``Agent Tool Call`` (only ``code_ref`` is), so Phase 5 must
		# re-supply it at approval time — e.g. from the pending tool invocation
		# context, or by re-issuing the tool call once the approval is granted.
		# The ``acting_user`` captured at dispatch time must be re-supplied the
		# same way — broker calls impersonate the ORIGINAL requester, never the
		# approver who granted the execution.
		# OPEN QUESTION: where the raw code is held between park and approval.

		return {
			"success": True,
			"status": "Pending Approval",
			"agent_tool_call": call.name,
			"approval": approval.name,
			"code_ref": code_ref,
			"message": "Execution paused pending approval.",
		}

	# 8c. Auto Approve (default) — enqueue immediately.
	enqueue_execution(call.name, code, snapshot, acting_user=acting_user)

	call.status = "Queued"
	call.save(ignore_permissions=True)

	return {
		"success": True,
		"status": "Queued",
		"agent_tool_call": call.name,
		"code_ref": code_ref,
	}


# ---------------------------------------------------------------------------
# E2 — RQ enqueue
# ---------------------------------------------------------------------------


def enqueue_execution(
	agent_tool_call_name: str,
	code: str,
	profile_snapshot: dict,
	acting_user: str | None = None,
) -> None:
	"""Enqueue :func:`execute_job` on the ``code-execution`` RQ queue.

	The job ``timeout`` is the profile's wall limit plus a fixed grace buffer so
	the RQ hard-timeout does not fire before the sandbox's own wall-clock kill.

	``acting_user`` is the session user captured at dispatch time. The worker
	impersonates it for every broker call — the worker itself runs as a
	privileged/system user and must never leak that identity into the broker.
	When it is missing the broker denies every call (fail closed).
	"""
	limits = (profile_snapshot or {}).get("limits") or {}
	wall = int(limits.get("max_wall_time_s") or DEFAULT_WALL_TIME_S)

	frappe.enqueue(
		"huf.ai.tools.code_execution.execute_job",
		queue="code-execution",
		timeout=wall + RQ_WALL_GRACE_S,
		agent_tool_call_name=agent_tool_call_name,
		code=code,
		profile_snapshot=profile_snapshot,
		acting_user=acting_user,
		now=bool(getattr(frappe.flags, "in_test", False)),
	)


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
			frappe.log_error(
				f"broker call {capability!r} failed: {exc}", "Huf Code Execution Broker"
			)
			return False, f"{type(exc).__name__}: {exc}"

	broker_handler.call_counts = call_counts
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
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert()
	return {"doctype": doctype, "name": doc.name}


def _op_doc_update(params: dict) -> dict:
	doctype = _require_str(params, "doctype", "doc.update")
	name = _require_str(params, "name", "doc.update")
	values = params.get("values")
	if not isinstance(values, dict):
		raise ValueError("doc.update 'values' must be a dict of field values")
	doc = frappe.get_doc(doctype, name)
	doc.update(values)
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


# ---------------------------------------------------------------------------
# E3 — RQ worker entrypoint
# ---------------------------------------------------------------------------


def _approval_blocks(call_name: str) -> str | None:
	"""Return a blocking reason if an approval exists and is not Approved.

	Safety net for the Phase 5 approval→enqueue path: an execution that was
	parked must not run unless its ``Agent Execution Approval`` is "Approved".
	Auto-approve executions have no approval row, so they pass straight through.
	"""
	rows = frappe.get_all(
		"Agent Execution Approval",
		filters={"agent_tool_call": call_name},
		fields=["status"],
		limit=1,
	)
	if not rows:
		return None
	status = rows[0].status
	if status == "Approved":
		return None
	return f"Approval not granted (status: {status})."


def execute_job(
	agent_tool_call_name: str,
	code: str,
	profile_snapshot: dict,
	acting_user: str | None = None,
) -> None:
	"""RQ worker: run the sandboxed interpreter and record the outcome.

	Runs inside a Frappe background worker process; the actual isolation happens
	in a fresh child interpreter spawned by :func:`run_sandboxed`. Broker RPCs
	from sandboxed code are authorized against ``profile_snapshot`` and executed
	impersonating ``acting_user`` (see :func:`_make_broker_handler`); when
	``acting_user`` is missing the broker denies every call (fail closed).
	"""
	call = frappe.get_doc("Agent Tool Call", agent_tool_call_name)
	limits = (profile_snapshot or {}).get("limits") or {}
	max_output = int(limits.get("max_output_bytes") or DEFAULT_MAX_OUTPUT_BYTES)

	# Do not run if a (Phase 5) approval exists and was not granted.
	blocked = _approval_blocks(call.name)
	if blocked:
		call.status = "Failed"
		call.error_message = blocked
		call.exit_status = "Error"
		call.save(ignore_permissions=True)
		return

	call.status = "Started"
	call.save(ignore_permissions=True)

	broker_handler = _make_broker_handler(profile_snapshot, acting_user)

	scratch_dir = tempfile.mkdtemp(prefix="huf-exec-")
	try:
		result: ExecutionResult = run_sandboxed(
			code, limits=limits, scratch_dir=scratch_dir, broker_handler=broker_handler
		)
		_apply_result(call, result, max_output, broker_calls=broker_handler.call_counts)
	except Exception as exc:  # noqa: BLE001 - never leave the row stuck at Started
		call.status = "Failed"
		call.exit_status = "Error"
		call.error_message = _truncate(
			f"{type(exc).__name__}: {exc}\n{frappe.get_traceback()}", 60000
		)
		call.limits_hit = 0
		call.save(ignore_permissions=True)
		frappe.log_error(
			f"execute_job failed for {agent_tool_call_name}: {exc}",
			"Huf Code Execution",
		)
	finally:
		shutil.rmtree(scratch_dir, ignore_errors=True)


def _apply_result(
	call, result: ExecutionResult, max_output: int, broker_calls: dict | None = None
) -> None:
	"""Map an :class:`ExecutionResult` onto the ``Agent Tool Call`` audit row."""
	ok = result.exit_status == "Ok"

	call.status = "Completed" if ok else "Failed"
	call.exit_status = result.exit_status  # already Title Case (Ok/Timeout/...)
	call.limits_hit = 1 if result.limits_hit else 0
	call.resource_usage = {
		"cpu_s": round(result.cpu_s, 4),
		"wall_s": round(result.wall_s, 4),
		"mem_mb_peak": None if result.mem_mb_peak is None else round(result.mem_mb_peak, 2),
		"output_bytes": int(result.output_bytes),
		# Per-capability count of authorized broker calls (Phase 4a). Call
		# arguments and results are deliberately NOT recorded on the audit row.
		"broker_calls": {key: int(value) for key, value in sorted((broker_calls or {}).items())},
	}
	# Match the codebase convention of wrapping scalar tool output as
	# {"output": "..."} (see ``agent_integration.process_tool_call``).
	call.tool_result = {"output": _truncate(result.stdout, max_output) or ""}

	if not ok:
		call.error_message = _truncate(result.stderr, 60000)
	else:
		call.error_message = None

	call.save(ignore_permissions=True)
