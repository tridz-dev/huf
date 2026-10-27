"""Retire confirmed-dead AI Models (used only by huf.patches.v1.refresh_model_catalogue).

For each ``huf.ai.model_catalogue.RETIRED`` entry whose row exists on the site
with the expected provider:

1. repoint configuration rows (Agents, allowed-model rows, Automations,
   conversations, Agent Settings) to the same-provider replacement. Every
   repoint leaves an Info Comment on the affected document (the parent Agent
   for allowed-model rows) naming the field, the old and the new model;
2. delete the old row only when no run history or configuration references it
   any more. Never force-deletes; anything still linked is left in place.

Each model is isolated: a failure is logged to Error Log and the sweep moves on.
Not called from after_migrate, so a model an admin re-adds later is never
repointed again.
"""

from __future__ import annotations

import frappe

from huf.ai.model_catalogue import RETIRED

AI_MODEL = "AI Model"

# Configuration links that are repointed to the replacement model.
CONFIG_LINKS: tuple[tuple[str, str], ...] = (
	("Agent", "model"),
	("Agent", "tts_model"),
	("Agent", "stt_model"),
	("Agent", "summary_model"),
	("Agent", "image_generation_model"),
	("Agent Allowed Model", "model"),
	("Automation", "model_override"),
	("Agent Conversation", "model"),
)
CHILD_DOCTYPES = {"Agent Allowed Model"}
# Single doctypes carrying an AI Model link.
SINGLE_LINKS: tuple[tuple[str, str], ...] = (("Agent Settings", "default_model"),)
# Historical records: never rewritten; their presence blocks deletion.
HISTORY_LINKS: tuple[tuple[str, str], ...] = (
	("Agent Run", "model"),
	("Agent Message", "model"),
	("Agent Message", "tts_model"),
	("Agent Message", "stt_model"),
	("Agent Run Feedback", "model"),
)


def _note(doctype: str, name: str, field: str, old: str, new: str) -> None:
	ref_doctype, ref_name = doctype, name
	if doctype in CHILD_DOCTYPES:
		ref_doctype = frappe.db.get_value(doctype, name, "parenttype") or "Agent"
		ref_name = frappe.db.get_value(doctype, name, "parent")
	message = (
		f"AI model catalogue refresh: {field} changed from {old} to {new} "
		f"because {old} has been retired by its provider."
	)
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": ref_doctype,
			"reference_name": ref_name,
			"content": message,
		}
	).insert(ignore_permissions=True)
	frappe.logger("huf.model_catalogue").info(f"{ref_doctype} {ref_name}: {message}")


def repoint_config(old: str, new: str) -> int:
	moved = 0
	for doctype, field in CONFIG_LINKS:
		for name in frappe.get_all(doctype, filters={field: old}, pluck="name"):
			frappe.db.set_value(doctype, name, field, new, update_modified=False)
			_note(doctype, name, field, old, new)
			moved += 1
	for doctype, field in SINGLE_LINKS:
		if frappe.db.get_single_value(doctype, field) == old:
			frappe.db.set_single_value(doctype, field, new)
			_note(doctype, doctype, field, old, new)
			moved += 1
	return moved


def _history_refs(model_name: str) -> list[str]:
	return [
		f"{doctype}.{field}"
		for doctype, field in HISTORY_LINKS
		if frappe.db.exists(doctype, {field: model_name})
	]


def retire_models(retired=RETIRED) -> dict:
	repointed, deleted, kept, failed = 0, [], [], []
	for old, (provider, new) in retired.items():
		try:
			if not frappe.db.exists(AI_MODEL, old):
				continue
			if frappe.db.get_value(AI_MODEL, old, "provider") != provider:
				# Same name, different provider: an admin's own row. Leave it.
				continue
			if not frappe.db.exists(AI_MODEL, new):
				kept.append(old)
				continue
			repointed += repoint_config(old, new)
			refs = _history_refs(old)
			if refs:
				kept.append(old)
				frappe.logger("huf.model_catalogue").info(
					f"AI Model {old} is retired but still referenced by {', '.join(refs)}; left in place."
				)
				continue
			try:
				# Never force=True: Frappe's link guard catches references this
				# module does not know about.
				frappe.delete_doc(AI_MODEL, old, ignore_permissions=True)
				deleted.append(old)
			except frappe.LinkExistsError:
				kept.append(old)
		except Exception:  # noqa: BLE001 -- per-model isolation, logged
			failed.append(old)
			frappe.log_error(
				title="huf: AI Model retirement failed",
				message=f"{old}\n\n{frappe.get_traceback()}",
			)
	return {"repointed": repointed, "deleted": deleted, "kept": kept, "failed": failed}
