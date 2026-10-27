"""Refresh the AI Model catalogue on existing sites (catalogue as of 2026-10-22).

Upserts the catalogue (adds the new is_latest_alias flag), then retires the
models huf.ai.model_catalogue.RETIRED lists as confirmed gone: configuration
rows are repointed to the same-provider replacement with an Info Comment on
each affected document, and the old row is deleted only when nothing,
including run history, references it. Safe to re-run.
"""

import frappe


def execute():
	frappe.reload_doc("huf", "doctype", "ai_model")
	from huf.ai.model_catalogue_retire import retire_models
	from huf.ai.model_catalogue_sync import upsert_models

	upserted = upsert_models()
	retired = retire_models()
	frappe.logger("huf.model_catalogue").info(f"refresh_model_catalogue: {upserted} {retired}")
