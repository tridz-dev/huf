# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Preview check: every audience a broadcast includes must have been collected for the template's purpose.

Run by ``limits.preview`` and therefore again inside ``runner.start``: Meta can recategorize a template after
approval, so the category is read from the template record each time, never from the broadcast snapshot.
"""

from __future__ import annotations

from typing import Any

import frappe

from huf.ai.whatsapp.broadcast.audiences import membership as aud

CODE = "audience_purpose_mismatch"


def included_audiences(broadcast: str) -> list[str]:
	"""Names of the audiences picked (not excluded) on a broadcast, in pick order."""
	rows = frappe.get_all(
		aud.BROADCAST_AUDIENCE,
		filters={"parent": broadcast, "parenttype": aud.BROADCAST, "exclude": 0},
		fields=["audience"],
		order_by="idx asc",
		limit_page_length=0,
		parent_doctype=aud.BROADCAST,
		ignore_permissions=True,
	)
	return list(dict.fromkeys(r["audience"] for r in rows if r.get("audience")))


def purpose_issues(broadcast: str, category: str | None) -> list[dict[str, Any]]:
	"""Blocking entries (``{code, message, limit_key}``) for included audiences lacking the category's purpose."""
	needed = aud.purpose_for_category(category)
	if not needed:
		return []
	out = []
	for name in included_audiences(broadcast):
		row = frappe.db.get_value(aud.AUDIENCE, name, ["title", *aud._PURPOSE_FIELD.values()], as_dict=True)
		if row and needed not in aud.purposes_of(row):
			out.append(
				{
					"code": CODE,
					"message": f"{row.get('title') or name} was not collected for {needed} messages, "
					f"which is what this {str(category).lower()} template is.",
					"limit_key": None,
				}
			)
	return out
