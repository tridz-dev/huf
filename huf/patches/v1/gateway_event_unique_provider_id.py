# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Bring existing Gateway Events under the one-row-per-(gateway, provider event ID) key.

Rows written by ingest already carry the derived key. Any other row with a provider id is re-keyed,
so a redelivery of it is recognised. When two old rows share a pair, the one already holding the key
(else the oldest) takes it and the others are left untouched: audit rows are never deleted.
"""

import frappe

from huf.ai.gateway_core.event_helpers import _idempotency_key


def execute():
	frappe.reload_doc("huf", "doctype", "gateway_event")
	rows = frappe.db.sql(
		"""SELECT name, gateway, provider_event_id FROM `tabGateway Event`
		WHERE IFNULL(provider_event_id, '') != ''
		AND idempotency_key != SHA2(CONCAT(gateway, ':', provider_event_id), 256)
		ORDER BY creation, name""",
		as_dict=True,
	)
	for row in rows:
		key = _idempotency_key(row.gateway, row.provider_event_id)
		if not frappe.db.exists("Gateway Event", {"idempotency_key": key}):
			frappe.db.set_value("Gateway Event", row.name, "idempotency_key", key, update_modified=False)
