"""Apply huf.ai.model_catalogue to the site's AI Model table.

Shared by ``huf.install.create_demo_ai_models`` (after_migrate) and the
``huf.patches.v1.refresh_model_catalogue`` patch so that both run the exact
same, idempotent sequence:

1. upsert every catalogue model (insert missing rows; on existing rows fill
   blank metadata, add missing catalogue modalities, and keep the seed-owned
   ``is_latest_alias`` flag in step with the catalogue);
2. repoint configuration rows (Agents, allowed-model lists, Agent Settings,
   Automations, conversations) that still use a retired model to the
   catalogue's replacement -- logged per row;
3. delete each retired model that nothing references any more. A retired
   model still referenced by run history (Agent Run / Agent Message / Agent
   Run Feedback) or by configuration with no replacement is left in place
   and logged, never force-deleted.

Only a narrow slice of the frappe API is used on purpose (see
huf/ai/tests/test_model_catalogue_refresh.py, which runs this module against
an in-memory stand-in for frappe).
"""

from __future__ import annotations

import frappe

from huf.ai.model_catalogue import MODELS, RETIRED

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

_FILL_FIELDS = ("context_window", "max_output_tokens", "supports_reasoning")


def _log():
	return frappe.logger("huf.model_catalogue")


def _merge_modalities(current: str | None, wanted: str | None) -> str | None:
	have = [m for m in (current or "").split(",") if m]
	for m in (wanted or "").split(","):
		if m and m not in have:
			have.append(m)
	return ",".join(have) or None


def upsert_models(models=MODELS) -> dict:
	inserted = updated = 0
	for m in models:
		try:
			name = m["model_name"]
			alias = 1 if m.get("is_latest_alias") else 0
			if not frappe.db.exists(AI_MODEL, name):
				doc = frappe.get_doc(dict(m, doctype=AI_MODEL, is_latest_alias=alias))
				doc.flags.ignore_mandatory = True
				doc.flags.ignore_validate = True
				doc.insert(ignore_permissions=True)
				inserted += 1
				continue

			row = (
				frappe.db.get_value(
					AI_MODEL, name, ["modalities", "is_latest_alias", *_FILL_FIELDS], as_dict=True
				)
				or {}
			)
			changes = {}
			merged = _merge_modalities(row.get("modalities"), m.get("modalities"))
			if merged != (row.get("modalities") or None):
				changes["modalities"] = merged
			for field in _FILL_FIELDS:
				if m.get(field) and not row.get(field):
					changes[field] = m[field]
			if int(row.get("is_latest_alias") or 0) != alias:
				changes["is_latest_alias"] = alias
			if changes:
				frappe.db.set_value(AI_MODEL, name, changes, update_modified=False)
				updated += 1
		except Exception:  # noqa: BLE001 -- per-row isolation, logged
			frappe.log_error(
				title="huf: AI Model seed skipped",
				message=f"{m.get('model_name')}\n\n{frappe.get_traceback()}",
			)
	return {"inserted": inserted, "updated": updated}


def _history_refs(model_name: str) -> list[str]:
	refs = []
	for doctype, field in HISTORY_LINKS:
		if frappe.db.exists(doctype, {field: model_name}):
			refs.append(f"{doctype}.{field}")
	return refs


def repoint_config(old: str, new: str | None) -> list[str]:
	"""Move configuration rows off ``old``. Returns the rows still on it."""
	left: list[str] = []
	for doctype, field in CONFIG_LINKS:
		for name in frappe.get_all(doctype, filters={field: old}, pluck="name"):
			if new and frappe.db.exists(AI_MODEL, new):
				frappe.db.set_value(doctype, name, field, new, update_modified=False)
				_log().info(f"Repointed {doctype} {name}.{field}: retired AI Model {old} -> {new}")
			else:
				left.append(f"{doctype} {name}.{field}")
	for doctype, field in SINGLE_LINKS:
		if frappe.db.get_single_value(doctype, field) == old:
			if new and frappe.db.exists(AI_MODEL, new):
				frappe.db.set_single_value(doctype, field, new)
				_log().info(f"Repointed {doctype}.{field}: retired AI Model {old} -> {new}")
			else:
				left.append(f"{doctype}.{field}")
	return left


def retire_models(retired=RETIRED) -> dict:
	deleted, kept = [], []
	for old, new in retired.items():
		if not frappe.db.exists(AI_MODEL, old):
			continue
		blockers = repoint_config(old, new) + _history_refs(old)
		if blockers:
			kept.append(old)
			_log().info(
				f"AI Model {old} is retired but still referenced by {', '.join(blockers)}; left in place."
			)
			continue
		try:
			# Never force=True: Frappe's link guard is the last line of defence
			# for a reference this module does not know about.
			frappe.delete_doc(AI_MODEL, old, ignore_permissions=True)
			deleted.append(old)
		except frappe.LinkExistsError:
			kept.append(old)
			_log().info(f"AI Model {old} is retired but still linked; left in place.")
	return {"deleted": deleted, "kept": kept}


def sync_catalogue() -> dict:
	"""Upsert the catalogue, then retire stale models. Idempotent."""
	result = upsert_models()
	result.update(retire_models())
	return result
