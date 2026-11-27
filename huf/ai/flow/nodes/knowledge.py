"""``knowledge.search`` node: search one Knowledge Source as the run's user.

Config: ``query`` (expression resolved against the run context), ``knowledge_source`` (name),
``top_k`` (1..MAX_TOP_K, default 5), ``filters`` (optional metadata dict).
Output ``{"passages": [{"text", "title", "score", "source", "chunk_id", "ref"}, ...]}``.

Policy:
* The AI kill switch applies (site ``huf_ai_disabled`` or a ``huf_ai_feature_map`` provider): a switched-off
  site fails the step with reason ``ai_disabled``; the run's budget deadline is checked too when present.
* The run's user must have read permission on the Knowledge Source; nothing uses ``ignore_permissions``.
* ``result`` (what the trace stores) is PII-masked; the query is masked as a whole. ``output`` carries
  the passages unmasked for later steps.
"""

from __future__ import annotations

import frappe

from huf.ai.flow.support.pii_mask import mask_pii
from huf.ai.knowledge.retriever import knowledge_search
from huf.ai.run_budget import AI_DISABLED, AIDisabled, RunBudgetExceeded, assert_ai_enabled

NODE_TYPE = "knowledge.search"
KEYS = frozenset({"query", "knowledge_source", "top_k", "filters"})
DEFAULT_TOP_K = 5
MAX_TOP_K = 20
PASSAGE_KEYS = ("text", "title", "score", "source", "chunk_id", "ref")


def _failed(message: str, reason: str | None = None) -> dict:
	out = {"status": "failed", "error": message}
	if reason:
		out["reason_code"] = reason
	return out


def _ai_block(run_ctx) -> dict | None:
	"""A failed result when AI is switched off or the run budget is spent, else None."""
	try:
		assert_ai_enabled(getattr(run_ctx, "agent", None))
		budget = getattr(run_ctx, "budget", None)
		if budget is not None:
			budget.check_deadline()
	except AIDisabled:
		return _failed("AI features are switched off on this site, so this search did not run.", AI_DISABLED)
	except RunBudgetExceeded:
		return _failed("This run has used up its time budget, so this search did not run.", "run_budget_exceeded")
	return None


def _top_k(value) -> int | str:
	if value is None:
		return DEFAULT_TOP_K
	if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_TOP_K:
		return f"Set how many results to return as a whole number from 1 to {MAX_TOP_K}."
	return value


def _source_error(source) -> str | None:
	if not isinstance(source, str) or not source:
		return "Choose the knowledge source this step should search."
	if not frappe.db.exists("Knowledge Source", source):
		return f'The knowledge source "{source}" does not exist. Open the step and pick it again.'
	if not frappe.has_permission("Knowledge Source", "read", source):
		return f'You do not have permission to search the knowledge source "{source}". Ask an admin for access.'
	return None


def exec_knowledge_search(node: dict, config: dict, context, run_ctx) -> dict:
	unknown = sorted(set(config) - KEYS)
	if unknown or "query" not in config or "knowledge_source" not in config:
		return _failed("Set the search text and knowledge source, and remove any settings this step does not use.")
	if blocked := _ai_block(run_ctx):
		return blocked
	top_k = _top_k(config.get("top_k"))
	if isinstance(top_k, str):
		return _failed(top_k)
	source = config["knowledge_source"]
	if error := _source_error(source):
		return _failed(error)
	query = context.resolve(config["query"])
	if not isinstance(query, str) or not query.strip():
		return _failed("The search text is empty. Check the value this step searches for.")
	filters = context.resolve(config["filters"]) if "filters" in config else None
	if filters is not None and not isinstance(filters, dict):
		return _failed("Set the search filters as field and value pairs.")

	rows = knowledge_search(query=query, knowledge_source=source, top_k=top_k, filters=filters)
	passages = [{k: row.get(k) for k in PASSAGE_KEYS} for row in (rows or [])[:top_k]]
	output = {"passages": passages}
	masked = mask_pii({"query": query, "passages": passages}, extra_fields=("query",))
	result = masked if masked is not None else {"query": "[masked]", "passages_count": len(passages)}
	return {"status": "success", "result": result, "output": output}
