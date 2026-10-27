"""Upsert huf.ai.model_catalogue into the site's AI Model table.

Called from ``huf.install.create_demo_ai_models`` on every after_migrate.
Additive only: inserts missing catalogue models and, on existing rows, fills
blank metadata, adds missing catalogue modalities and keeps the seed-owned
``is_latest_alias`` flag in step with the catalogue. It never deletes or
repoints anything, so an admin's own rows and choices survive every migrate.

Only a narrow slice of the frappe API is used on purpose (see
huf/ai/tests/test_model_catalogue_refresh.py, which runs this module against
an in-memory stand-in for frappe).
"""

from __future__ import annotations

import frappe

from huf.ai.model_catalogue import MODELS

AI_MODEL = "AI Model"

_FILL_FIELDS = ("context_window", "max_output_tokens", "supports_reasoning")


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
