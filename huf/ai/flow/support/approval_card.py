"""The one description of a pending approval that every channel shows: bell, run page, email, Slack.

A card is a headline (``Approval needed: Refund review``), a lead sentence (what the flow's author wrote),
and a few labelled facts taken from the data the run started with. No flow id, run id, step id or JSON ever
appears; the channels link to the run instead. The wording lives in ``huf.ai.flow.support.humanize``.
"""

from __future__ import annotations

import html
import json

from huf.ai.flow.support import humanize

MAX_SLACK_DETAILS = 400


def flow_name_of(flow_run) -> str:
	"""The title a person gave the flow, or an empty string when it is only known by its id."""
	try:
		import frappe

		flow_id = getattr(flow_run, "flow_id", None)
		if not flow_id:
			return ""
		name = frappe.db.get_value("Flow Definition", flow_id, "flow_name")
		return str(name or "") if name and name != flow_id else ""
	except Exception:
		return ""


def waiting_of(flow_run) -> dict:
	raw = getattr(flow_run, "waiting", None)
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
	except (ValueError, TypeError):
		return {}
	return data if isinstance(data, dict) else {}


def build_card(flow_name: str | None, waiting: dict | None) -> dict:
	"""``{"headline", "lead", "facts", "facts_text", "sentence"}`` from a run's ``waiting`` data.

	Uses the keys the engine stored when the run paused (``headline``, ``facts``) and falls back to the
	message for runs that paused before those keys existed.
	"""
	waiting = waiting or {}
	name = flow_name if flow_name is not None else (waiting.get("flow_name") or "")
	facts = [f for f in (waiting.get("facts") or []) if isinstance(f, dict) and f.get("label") and f.get("value")]
	lead = humanize.approval_lead(name, waiting.get("message"))
	facts_text = humanize.facts_sentence(facts)
	return {
		"headline": waiting.get("headline") or humanize.approval_headline(name),
		"lead": lead,
		"facts": facts,
		"facts_text": facts_text,
		"sentence": humanize.approval_sentence(name, waiting.get("step_title"), waiting.get("message"), facts),
	}


def facts_html(facts: list[dict]) -> str:
	rows = "".join(
		f'<tr><td style="padding:2px 12px 2px 0;color:#666">{html.escape(str(f["label"]))}</td>'
		f'<td style="padding:2px 0"><strong>{html.escape(str(f["value"]))}</strong></td></tr>'
		for f in facts
	)
	return f'<table style="border-collapse:collapse;margin:8px 0">{rows}</table>' if rows else ""


def slack_details(card: dict) -> str:
	"""Lead sentence plus one ``Label: value`` line per fact, short enough for a card."""
	lines = [card["lead"]] + [f"{f['label']}: {f['value']}" for f in card["facts"]]
	text = "\n".join(lines)
	return text if len(text) <= MAX_SLACK_DETAILS else text[: MAX_SLACK_DETAILS - 1].rstrip() + "…"


def waiting_fields(flow_run, node: dict, rendered_message: str, payload: dict) -> dict:
	"""What the engine stores on ``waiting`` so every channel can show the same card (message sentence, headline, facts)."""
	from huf.ai.graph.error_copy import step_title

	name = flow_name_of(flow_run)
	facts = humanize.key_facts(payload)
	return {
		"message": humanize.approval_lead(name, rendered_message),
		"headline": humanize.approval_headline(name),
		"flow_name": name,
		"step_title": step_title(node),
		"facts": facts,
		"context_summary": humanize.facts_sentence(facts),
	}
