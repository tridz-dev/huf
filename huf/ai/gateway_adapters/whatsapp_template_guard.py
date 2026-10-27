"""Guard + sidecar for Huf-owned WhatsApp templates.

Huf pushes templates straight to Meta and mirrors a row into frappe_whatsapp's
``WhatsApp Templates``. frappe_whatsapp's own controller would re-push a lossy payload on
any later save, so saves/deletes of Huf-owned rows are refused unless they come from Huf's
own code (``frappe.flags.huf_template_write`` / ``huf_template_write()``).

This module must stay import-safe on sites without frappe_whatsapp: it never imports it.
"""

import contextlib

import frappe
from frappe.utils import now_datetime

TEMPLATE_DOCTYPE = "WhatsApp Templates"
EXTRA_DOCTYPE = "WhatsApp Template Extra"
WRITE_FLAG = "huf_template_write"
MIRROR_FLAG = "huf_mirror"
MANAGED_MSG = "This template is managed by Huf. Edit it from the WhatsApp page."
JSON_FIELDS = ("named_samples", "components_json")
EXTRA_FIELDS = (
	"template_id",
	"parameter_format",
	"named_samples",
	"ttl_seconds",
	"header_format",
	"components_json",
	"created_via",
	"last_synced_at",
)


def _key(account, template):
	from huf.ai.gateway_adapters.whatsapp_bridge import state_key

	return state_key(account, template)


@contextlib.contextmanager
def huf_template_write():
	"""Mark the enclosed block as Huf's own write path (bypasses the desk guard)."""
	prev = getattr(frappe.flags, WRITE_FLAG, None)
	setattr(frappe.flags, WRITE_FLAG, True)
	try:
		yield
	finally:
		setattr(frappe.flags, WRITE_FLAG, prev)


def _extra_available():
	try:
		return bool(frappe.db.table_exists(EXTRA_DOCTYPE))
	except Exception:
		return False


def get_extra(account, template) -> dict | None:
	"""Template Extra as a dict (JSON fields decoded) or None."""
	if not template or not _extra_available():
		return None
	row = frappe.db.get_value(EXTRA_DOCTYPE, _key(account, template), ["*"], as_dict=True)
	if not row:
		return None
	row = dict(row)
	for f in JSON_FIELDS:
		if isinstance(row.get(f), str) and row[f]:
			try:
				row[f] = frappe.parse_json(row[f])
			except Exception:
				pass
	return row


def upsert_extra(account, template, **fields) -> str:
	"""Create/update the Template Extra for (account, template); returns its name.

	Unknown fields raise; dict/list values are stored as JSON. ``last_synced_at`` defaults to now.
	"""
	unknown = set(fields) - set(EXTRA_FIELDS)
	if unknown:
		raise frappe.ValidationError(f"Unknown WhatsApp Template Extra field(s): {sorted(unknown)}")
	key = _key(account, template)
	fields.setdefault("last_synced_at", now_datetime())
	for f in JSON_FIELDS:
		if f in fields and not isinstance(fields[f], str) and fields[f] is not None:
			fields[f] = frappe.as_json(fields[f])
	if frappe.db.exists(EXTRA_DOCTYPE, key):
		doc = frappe.get_doc(EXTRA_DOCTYPE, key)
	else:
		doc = frappe.new_doc(EXTRA_DOCTYPE)
		doc.state_key = key
		doc.whatsapp_account = account
		doc.template = template
	doc.update(fields)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.name


def delete_extra(account, template) -> None:
	if _extra_available() and frappe.db.exists(EXTRA_DOCTYPE, _key(account, template)):
		frappe.delete_doc(EXTRA_DOCTYPE, _key(account, template), ignore_permissions=True, force=True)


def is_huf_owned(doc) -> bool:
	"""True when the row was created by Huf (Extra.created_via == Huf) or carries flags.huf_mirror."""
	if doc.flags.get(MIRROR_FLAG):
		return True
	name = doc.get("name")
	if not name:
		return False
	account = doc.get("whatsapp_account") or frappe.db.get_value(TEMPLATE_DOCTYPE, name, "whatsapp_account")
	extra = get_extra(account, name)
	return bool(extra and extra.get("created_via") == "Huf")


def _huf_write_allowed(doc) -> bool:
	return bool(frappe.flags.get(WRITE_FLAG) or doc.flags.get(WRITE_FLAG))


def guard_template_write(doc, method=None):
	"""doc_events handler (before_validate/validate/before_save/on_trash) for ``WhatsApp Templates``."""
	if _huf_write_allowed(doc):
		return
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
		return
	if method != "on_trash" and doc.is_new():
		return
	if is_huf_owned(doc):
		frappe.throw(MANAGED_MSG, exc=frappe.ValidationError)


def __getattr__(name):
	"""Lazy ``GuardedWhatsAppTemplates``: controller subclass for ``override_doctype_class``.

	Needed for on_trash: Frappe runs the controller method BEFORE doc_events, so only a
	subclass can stop frappe_whatsapp's Meta DELETE. Resolved lazily so this module imports
	on sites without frappe_whatsapp.
	"""
	if name != "GuardedWhatsAppTemplates":
		raise AttributeError(name)
	from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import (
		WhatsAppTemplates,
	)

	class GuardedWhatsAppTemplates(WhatsAppTemplates):
		def validate(self):
			guard_template_write(self, "validate")
			super().validate()

		def on_trash(self):
			guard_template_write(self, "on_trash")
			super().on_trash()

	globals()[name] = GuardedWhatsAppTemplates
	return GuardedWhatsAppTemplates
