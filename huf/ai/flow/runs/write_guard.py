# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Run records are written by server code only.

``Agent Flow Run`` and ``Flow Member State`` feed trusted decisions (recorded approvals, reply window, live or test
mode), and ``read_only`` fields are a form hint, not a guard. Their DocPerm write/create rows stay, because the run
actions (cancel, continue, start) check them, so the controllers refuse the writes instead.

Server code is recognised by ``ignore_permissions`` (or ``db_set``/``db.set_value``, which never reach a controller).
``flags`` is a reserved key in Frappe, so no request payload can set it.
"""

import frappe
from frappe import _


def require_server_write(doc) -> None:
	if doc.flags.ignore_permissions:
		return
	refuse(doc)


def refuse(doc) -> None:
	frappe.throw(_("{0} records are written by Huf only.").format(_(doc.doctype)), frappe.PermissionError)
