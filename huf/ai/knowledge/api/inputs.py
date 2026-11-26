"""Whitelisted API for Knowledge Inputs: bulk delete and indexed-text preview."""

import json

import frappe
from frappe import _

MAX_BULK_DELETE = 1000
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
# Runs per deleted input (hooks.py doc_events). Bulk delete does the same work once per batch.
CLEANUP_HOOK = "huf.ai.knowledge.hooks.on_knowledge_input_deleted"


def _deny(message: str):
	frappe.throw(message, frappe.PermissionError)


def _parse_names(inputs) -> list[str]:
	if isinstance(inputs, str):
		try:
			inputs = json.loads(inputs)
		except ValueError:
			frappe.throw(_("inputs must be a JSON list of Knowledge Input names"))
	if not isinstance(inputs, list) or not inputs or not all(isinstance(n, str) and n for n in inputs):
		frappe.throw(_("inputs must be a non-empty list of Knowledge Input names"))
	names = list(dict.fromkeys(inputs))
	if len(names) > MAX_BULK_DELETE:
		frappe.throw(_("Delete at most {0} documents at a time").format(MAX_BULK_DELETE))
	return names


def _open_backend(source):
	from huf.ai.knowledge.backends import get_backend
	from huf.ai.knowledge.indexer import _build_backend_config

	backend = get_backend(source.knowledge_type)()
	backend.initialize(source.name, _build_backend_config(source))
	return backend


def _run_other_trash_hooks(doc) -> None:
	"""Run every on_trash doc event except the per-input stats cleanup (done once per batch)."""
	hooks = frappe.get_doc_hooks()
	handlers = list(hooks.get(doc.doctype, {}).get("on_trash", [])) + list(
		hooks.get("*", {}).get("on_trash", [])
	)
	for path in handlers:
		if path != CLEANUP_HOOK:
			frappe.get_attr(path)(doc, "on_trash")


def _delete_input(name: str, backend) -> None:
	"""Remove an input's chunks, then the document (its own on_trash cleanup is deferred)."""
	doc = frappe.get_doc("Knowledge Input", name)
	backend.delete_chunks(name)
	_run_other_trash_hooks(doc)
	frappe.delete_doc("Knowledge Input", name, ignore_on_trash=True)


@frappe.whitelist(methods=["POST"])
def bulk_delete_inputs(knowledge_source: str, inputs) -> dict:
	"""Delete several inputs of one source. Delete permission is checked per row.

	Returns ``{"deleted": [names], "failed": [{"name", "error"}]}``. Source stats and
	status are refreshed once at the end, not per row.
	"""
	if not frappe.has_permission("Knowledge Input", "delete"):
		_deny(_("Not permitted to delete Knowledge Inputs"))
	if not frappe.has_permission("Knowledge Source", "read", doc=knowledge_source):
		_deny(_("Not permitted to access Knowledge Source {0}").format(knowledge_source))
	names = _parse_names(inputs)

	source = frappe.get_doc("Knowledge Source", knowledge_source)
	backend = _open_backend(source)

	deleted: list[str] = []
	failed: list[dict] = []
	for name in names:
		if frappe.db.get_value("Knowledge Input", name, "knowledge_source") != source.name:
			failed.append({"name": name, "error": _("Not part of this knowledge source")})
			continue
		if not frappe.has_permission("Knowledge Input", "delete", doc=name):
			failed.append({"name": name, "error": _("Not permitted to delete this document")})
			continue
		savepoint = f"bulk_input_{len(deleted) + len(failed)}"
		frappe.db.savepoint(savepoint)
		try:
			_delete_input(name, backend)
		except Exception as exc:  # noqa: BLE001 - one bad row must not abort the batch
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(title="Knowledge bulk delete", message=frappe.get_traceback())
			failed.append({"name": name, "error": str(exc)[:200]})
		else:
			deleted.append(name)

	if deleted:
		from huf.ai.knowledge.hooks import recompute_source_status
		from huf.ai.knowledge.indexer import update_source_stats

		update_source_stats(source, backend)
		recompute_source_status(source.name)
	return {"deleted": deleted, "failed": failed}


@frappe.whitelist()
def get_input_chunks(knowledge_input: str, start: int = 0, limit: int = DEFAULT_PAGE_SIZE) -> dict:
	"""One page of the text indexed for an input (File, URL or Text), in document order.

	Needs read permission on the input's source. Returns ``supported: false`` for a
	backend that cannot list its chunks.
	"""
	source_name = frappe.db.get_value("Knowledge Input", knowledge_input, "knowledge_source")
	if (
		not source_name
		or not frappe.has_permission("Knowledge Source", "read", doc=source_name)
		or not frappe.has_permission("Knowledge Input", "read", doc=knowledge_input)
	):
		_deny(_("Not permitted to read this document"))

	start = max(int(start or 0), 0)
	limit = min(max(int(limit or DEFAULT_PAGE_SIZE), 1), MAX_PAGE_SIZE)
	source = frappe.get_doc("Knowledge Source", source_name)
	listed = _open_backend(source).get_chunks(knowledge_input, start, limit)
	if listed is None:
		return {"supported": False, "chunks": [], "total": 0, "start": start, "limit": limit}

	page, total = listed
	chunks = [
		{
			"index": (c.metadata or {}).get("chunk_index", start + i),
			"text": c.text,
			"page": (c.metadata or {}).get("page"),
			"page_end": (c.metadata or {}).get("page_end"),
		}
		for i, c in enumerate(page)
	]
	return {"supported": True, "chunks": chunks, "total": int(total), "start": start, "limit": limit}
