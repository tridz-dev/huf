# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Run records are written by server code only.

``Agent Flow Run`` and ``Flow Member State`` feed trusted decisions (recorded approvals, reply window, live or test
mode), and ``read_only`` fields are a form hint, not a guard. Their DocPerm write/create rows stay, because the run
actions (cancel, continue, start) check them, so the controllers refuse the writes instead.

Server code is recognised by ``ignore_permissions`` (or ``db_set``/``db.set_value``, which never reach a controller).
``flags`` is a reserved key in Frappe, so no request payload can set it.
"""

import inspect
import sys

import frappe
from frappe import _


def require_server_write(doc) -> None:
	if doc.flags.ignore_permissions or _is_engine_insert(doc):
		return
	refuse(doc)


def refuse(doc) -> None:
	frappe.throw(_("{0} records are written by Huf only.").format(_(doc.doctype)), frappe.PermissionError)


def _is_engine_insert(doc) -> bool:
	"""True while ``engine.create_flow_run`` is inserting this very document.

	It inserts with permission checks on when a signed-in user starts a flow, so it carries no flag. The caller's
	frame cannot be faked by a request, and it covers only the document the engine built.
	"""
	if doc.doctype != "Agent Flow Run":
		return False
	from huf.ai.flow import engine

	code = inspect.unwrap(engine.create_flow_run).__code__
	frame = sys._getframe()
	while frame:
		if frame.f_code is code:
			return frame.f_locals.get("flow_run") is doc
		frame = frame.f_back
	return False
