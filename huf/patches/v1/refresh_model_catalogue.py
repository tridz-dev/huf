"""Refresh the seeded AI Model catalogue on existing sites (catalogue as of 2026-10-22).

Upserts every model in huf.ai.model_catalogue.MODELS (including the new
``is_latest_alias`` flag), repoints Agents / allowed-model rows / Agent
Settings / Automations / conversations that use a retired model to the
catalogue's replacement (each repoint is logged to the "huf.model_catalogue"
logger), and deletes retired models nothing references. Models still
referenced by run history are kept. Safe to re-run: every step is idempotent.
"""

import frappe


def execute():
	frappe.reload_doc("huf", "doctype", "ai_model")
	from huf.ai.model_catalogue_sync import sync_catalogue

	result = sync_catalogue()
	frappe.logger("huf.model_catalogue").info(
		f"refresh_model_catalogue: inserted={result['inserted']} updated={result['updated']} "
		f"deleted={len(result['deleted'])} kept_referenced={result['kept']}"
	)
