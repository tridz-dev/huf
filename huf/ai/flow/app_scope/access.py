"""Delegated, app-scoped access to app-owned flows (D-HAPPIOL-EMBED decision 2).

An app declares, in its own ``hooks.py``, which of its own roles may act on the flows it owns::

    huf_flow_app_access = {"<app>": {"view": [roles], "edit": [roles], "test": [roles], "approve": [roles]}}

Rules, fail closed:

- Administrator, System Manager and Huf Manager pass (support access).
- A flow with an ``owner_app`` is reachable only by a user who holds one of that app's roles for the action.
  Huf User and Huf Viewer have no access to it.
- A Huf-native flow (empty ``owner_app``) keeps today's Huf-role rules: app roles alone never reach it.
- An app may only grant access to its own flows: an entry is read from the hooks of the app it names, so app B
  cannot grant roles on app A's flows. Huf and Frappe core roles are never accepted as delegated roles.
- ``edit`` implies ``view``. ``test`` and ``approve`` do not.
- An app may narrow its own grant per flow and user (for example to the records a user is restricted to)::

      huf_flow_app_narrow = {"<app>": "<dotted path>"}

  The function receives ``{"flow_id", "user", "action"}`` and only an exact ``True`` allows: anything else, an
  exception or a bad path refuses, so an app answers ``False`` for a flow it does not know. It only ever removes
  access, and applies to :func:`flow_access`, the Flow Definition ``has_permission`` hook and its list condition.
- App roles never read Agent Flow Run or Flow Member State documents (they hold raw payloads): they read runs
  only through the scoped, masked flow APIs.

Frappe ``has_permission`` hooks can only deny; the grant itself is a Custom DocPerm row synced by
:mod:`huf.ai.flow.app_scope.docperms`. The hooks below and the query conditions scope those rows to
``owner_app``.
"""

import frappe
from frappe import _

from huf.ai.flow.app_scope.ownership import FIELD, SERVER_FLAG, owner_app_of

HOOK = "huf_flow_app_access"
NARROW_HOOK = "huf_flow_app_narrow"
ACTIONS = ("view", "edit", "test", "approve")
PRIVILEGED_ROLES = frozenset({"System Manager", "Huf Manager"})
#: Huf roles that reach Huf-native flows today.
NATIVE_ROLES = frozenset({"Huf User", "Huf Viewer", "Huf Manager"})
#: Roles an app may never delegate: they are Huf's or Frappe's own.
PROTECTED_ROLES = frozenset(
	{"Administrator", "System Manager", "Guest", "All", "Desk User", "Huf User", "Huf Viewer", "Huf Manager"}
)
READ_PTYPES = frozenset({"read", "select", "report", "print", "email"})
#: Agent Flow Run and Flow Member State hold raw payloads: no app role reads or writes the documents.
RUN_DOCTYPES = ("Agent Flow Run", "Flow Member State")
_FLOW_FIELD = {"Agent Flow Run": "flow_definition", "Flow Member State": "flow"}
#: Flow Definition fields that only the app's server path (or a Huf Manager) may change on an app flow.
SERVER_ONLY_FIELDS = ("status", "live_send", "flow_id")


# --- grants -------------------------------------------------------------------------------------------------


def app_grants() -> dict[str, dict[str, frozenset]]:
	"""``{app: {action: roles}}`` for installed apps, each read only from that app's own hooks."""
	grants = {}
	for app in frappe.get_installed_apps():
		declared = (frappe.get_hooks(HOOK, app_name=app) or {}).get(app)
		if not isinstance(declared, dict):
			continue
		per_action = {}
		for action in ACTIONS:
			roles = declared.get(action) or []
			roles = [roles] if isinstance(roles, str) else roles
			per_action[action] = frozenset(
				r for r in roles if isinstance(r, str) and r and r not in PROTECTED_ROLES
			)
		per_action["view"] = per_action["view"] | per_action["edit"]
		grants[app] = per_action
	return grants


def is_privileged(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(PRIVILEGED_ROLES & set(frappe.get_roles(user)))


def apps_for(user: str | None, action: str) -> set[str]:
	"""Apps whose flows ``user`` may ``action`` through a delegated app role."""
	if action not in ACTIONS:
		return set()
	roles = set(frappe.get_roles(user or frappe.session.user))
	return {app for app, per_action in app_grants().items() if roles & per_action[action]}


def narrowers(app: str) -> list[str]:
	"""The app's own ``huf_flow_app_narrow`` paths for itself (empty: the app does not narrow)."""
	paths = (frappe.get_hooks(NARROW_HOOK, app_name=app) or {}).get(app) or []
	return [paths] if isinstance(paths, str) else list(paths)


def narrow_allows(app: str, user: str, flow: str, action: str) -> bool:
	"""Whether every narrowing function of ``app`` answers exactly ``True``. Fails closed."""
	path = None
	try:
		return all(
			frappe.get_attr(path)({"flow_id": flow, "user": user, "action": action}) is True
			for path in narrowers(app)
		)
	except Exception as exc:  # noqa: BLE001 - any failure refuses; the message may carry data, so only the class
		frappe.logger("huf").warning(f"{NARROW_HOOK} {path or app}: {type(exc).__name__}; access refused")
		return False


def _app_allows(user: str, app: str, flow: str, action: str) -> bool:
	return app in apps_for(user, action) and narrow_allows(app, user, flow, action)


def _has_native_role(user: str | None) -> bool:
	return bool(NATIVE_ROLES & set(frappe.get_roles(user or frappe.session.user)))


# --- decisions ----------------------------------------------------------------------------------------------


def flow_access(user: str | None, flow: str | None, action: str) -> bool:
	"""Whether ``user`` may ``action`` (view, edit, test, approve) the flow ``flow``. Unknown action or flow: no."""
	user = user or frappe.session.user
	if action not in ACTIONS or not flow or not frappe.db.exists("Flow Definition", flow):
		return False
	if is_privileged(user):
		return True
	owner = owner_app_of(flow)
	if owner:
		return _app_allows(user, owner, flow, action)
	return _native_access(user, action)


def _native_access(user: str, action: str) -> bool:
	"""Huf-native flows keep today's rules: a Huf role. Writes stay with DocPerm (Huf Manager)."""
	roles = set(frappe.get_roles(user))
	if action == "view":
		return bool(NATIVE_ROLES & roles)
	if action == "edit":
		return "Huf Manager" in roles
	return "Huf User" in roles


def require_flow_access(flow: str | None, action: str, user: str | None = None) -> None:
	if not flow_access(user, flow, action):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def approval_recipients(flow_run, users: list) -> list:
	"""``users`` who may be told about ``flow_run``'s approval. Huf-native flows: unchanged.

	App-owned flows: only users with ``approve`` access to the flow. It only removes users, and fails closed:
	a check that raises drops that user, an unreadable owner drops everyone.
	"""
	flow = getattr(flow_run, "flow_definition", None) or getattr(flow_run, "flow_id", None)
	try:
		if not (getattr(flow_run, "owner_app", None) or owner_app_of(flow)):
			return users
	except Exception as exc:  # noqa: BLE001
		_log_recipient_failure(flow_run, exc)
		return []

	def allowed(user):
		try:
			return flow_access(user, flow, "approve") is True
		except Exception as exc:  # noqa: BLE001
			_log_recipient_failure(flow_run, exc)
			return False

	return [user for user in users if allowed(user)]


def _log_recipient_failure(flow_run, exc: Exception) -> None:
	# Ids and the exception class only: the message may carry data.
	frappe.logger("huf").warning(
		f"approval recipient check for run {getattr(flow_run, 'name', None)}: {type(exc).__name__}; dropped"
	)


# --- has_permission hooks (deny only) -----------------------------------------------------------------------


def _doc_name(doc):
	return doc if isinstance(doc, str) else (doc.get("name") if doc else None)


def _stored_owner_app(doctype: str, doc) -> str | None:
	"""``owner_app`` as stored, never the in-memory value a caller could have tampered with."""
	name = _doc_name(doc)
	if doctype == "Flow Definition":
		return owner_app_of(name) if name and frappe.db.exists(doctype, name) else None
	flow = frappe.db.get_value(doctype, name, _FLOW_FIELD[doctype]) if name else None
	if flow is None and not isinstance(doc, str) and doc:
		flow = doc.get(_FLOW_FIELD[doctype])
	return owner_app_of(flow)


def has_permission_flow_definition(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if is_privileged(user):
		return True
	owner = _stored_owner_app("Flow Definition", doc)
	if not owner:
		return _has_native_role(user)
	if ptype in READ_PTYPES:
		return _app_allows(user, owner, _doc_name(doc), "view")
	if ptype == "write":
		return _app_allows(user, owner, _doc_name(doc), "edit")
	return False  # create, delete, share, export, import, submit, cancel, amend: never for an app role


def _has_permission_flow_record(doctype, doc, user):
	"""Agent Flow Run and Flow Member State: app-owned flows' documents are for privileged users only."""
	user = user or frappe.session.user
	if is_privileged(user):
		return True
	return not _stored_owner_app(doctype, doc) and _has_native_role(user)


def has_permission_flow_run(doc, ptype=None, user=None, debug=False):
	return _has_permission_flow_record("Agent Flow Run", doc, user)


def has_permission_member_state(doc, ptype=None, user=None, debug=False):
	return _has_permission_flow_record("Flow Member State", doc, user)


# --- permission_query_conditions ----------------------------------------------------------------------------


def flow_scope_condition(user: str | None = None, table: str = "tabFlow Definition") -> str | None:
	"""SQL condition on Flow Definition rows ``user`` may list; None means no extra restriction."""
	user = user or frappe.session.user
	if is_privileged(user):
		return None
	parts = []
	if _has_native_role(user):
		parts.append(f"ifnull(`{table}`.`{FIELD}`, '') = ''")
	apps = sorted(apps_for(user, "view"))
	whole = [app for app in apps if not narrowers(app)]
	if whole:
		parts.append(f"`{table}`.`{FIELD}` in ({_in(whole)})")
	flows = _narrowed_flows(user, [app for app in apps if app not in whole])
	if flows:
		parts.append(f"`{table}`.`name` in ({_in(flows)})")
	return "(" + " or ".join(parts) + ")" if parts else "1=0"


def _in(values) -> str:
	return ", ".join(frappe.db.escape(v) for v in values)


def _narrowed_flows(user: str, apps: list[str]) -> list[str]:
	"""The flows of the narrowing ``apps`` that ``user`` may view, asked one by one."""
	if not apps:
		return []
	rows = frappe.get_all("Flow Definition", filters={FIELD: ("in", apps)}, fields=["name", FIELD])
	return [r.name for r in rows if narrow_allows(r[FIELD], user, r.name, "view")]


def _scoped_by_flow(column: str, user) -> str | None:
	"""Documents of Huf-native flows only, for holders of a Huf role."""
	user = user or frappe.session.user
	if is_privileged(user):
		return None
	if not _has_native_role(user):
		return "1=0"
	sub = f"select `name` from `tabFlow Definition` where ifnull(`{FIELD}`, '') = ''"  # noqa: S608 -- constant
	return f"ifnull({column}, '') in ({sub})"


def get_run_permission_query_conditions(user=None):
	return _scoped_by_flow("`tabAgent Flow Run`.`flow_definition`", user)


def get_member_state_permission_query_conditions(user=None):
	return _scoped_by_flow("`tabFlow Member State`.`flow`", user)


# --- server-only writes on app flows ------------------------------------------------------------------------


def guard_server_only_fields(doc) -> None:
	"""Refuse a status or ``live_send`` change on an app flow unless it comes from the app's server path."""
	if doc.is_new() or doc.flags.get(SERVER_FLAG) or is_privileged():
		return
	if not owner_app_of(doc.name):
		return
	for field in SERVER_ONLY_FIELDS:
		if doc.has_value_changed(field):
			frappe.throw(
				_("Only the owning app can change {0} on this flow.").format(field), frappe.PermissionError
			)


def guard_app_flow_rename(doc, old_name: str, new_name: str, merge: bool = False) -> None:
	"""Refuse a rename or merge of (or into) an app flow: the app finds its flow, and parked runs their pin, by
	name. ``rename_doc`` needs only write permission and never runs ``validate``."""
	if doc.flags.get(SERVER_FLAG) or is_privileged():
		return
	if owner_app_of(old_name) or (merge and owner_app_of(new_name)):
		frappe.throw(_("Only the owning app can rename or merge this flow."), frappe.PermissionError)


def guard_server_only_db_set(doc, fieldname, value) -> None:
	if is_privileged() or not owner_app_of(doc.name):
		return
	changes = fieldname if isinstance(fieldname, dict) else {fieldname: value}
	if any(f in changes for f in SERVER_ONLY_FIELDS):
		frappe.throw(_("Only the owning app can change this on the flow."), frappe.PermissionError)


def set_app_flow_status(app: str, flow_id: str, status: str, *, live_send: bool | None = None):
	"""The app's server path for status and ``live_send``. Python only: deliberately not whitelisted."""
	if owner_app_of(flow_id) != app or not app:
		frappe.throw(_("Flow {0} is not owned by {1}.").format(flow_id, app), frappe.PermissionError)
	doc = frappe.get_doc("Flow Definition", flow_id)
	doc.status = status
	if live_send is not None:
		doc.live_send = 1 if live_send else 0
	doc.flags[SERVER_FLAG] = True
	doc.save(ignore_permissions=True)
	return doc
