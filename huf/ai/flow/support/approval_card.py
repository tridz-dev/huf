"""The one description of a pending approval that every channel shows: bell, run page, email, Slack.

A card is a title (the author's own, else ``Approval needed: Refund review``), a note (what the flow's author wrote),
and a few labelled facts: the ones the author chose with "Show these details to the approver" (``details``), else
the most telling facts of the data the run started with. In a test run it also carries a test note. No flow id,
run id, step id or JSON ever appears; the channels link to the run instead. The wording lives in
``huf.ai.flow.support.humanize``.

Shape served to the UI (``get_flow_run`` and ``get_pending_approvals`` as ``approval_card``)::

    {"title": "Approval needed: Refund review", "facts": [{"label": "Customer", "value": "Ada"}],
     "note": "Please check the amount.", "test_note": "Test: you can approve this yourself" | None}
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
	"""``{"title", "headline", "note", "lead", "test_note", "facts", "facts_text", "sentence"}`` from a run's ``waiting`` data.

	Uses the keys the engine stored when the run paused (``title``, ``headline``, ``facts``) and falls back to the
	message for runs that paused before those keys existed. ``headline`` is the same text as ``title`` and ``lead`` the
	same as ``note`` (the names the email, Slack and bell code already use).
	"""
	waiting = waiting or {}
	name = flow_name if flow_name is not None else (waiting.get("flow_name") or "")
	facts = [f for f in (waiting.get("facts") or []) if isinstance(f, dict) and f.get("label") and f.get("value")]
	lead = humanize.approval_lead(name, waiting.get("message"))
	facts_text = humanize.facts_sentence(facts)
	title = (waiting.get("title") or "").strip() or waiting.get("headline") or humanize.approval_headline(name)
	test_note = waiting.get("test_note") if waiting.get("test_run") else None
	sentence = humanize.approval_sentence(name, waiting.get("step_title"), waiting.get("message"), facts)
	return {
		"title": title,
		"headline": title,
		"note": lead,
		"lead": lead,
		"test_note": test_note,
		"facts": facts,
		"facts_text": facts_text,
		"sentence": f"{sentence} {test_note}." if test_note else sentence,
	}


def api_card(flow_name: str | None, waiting: dict | None, flow_id: str | None = None) -> dict:
	"""The card as the UI receives it: ``{"title", "facts", "note", "test_note"}`` and nothing else.

	A flow that is only known by its id (``flow_name == flow_id``) has no name to print.
	"""
	card = build_card(None if flow_name == flow_id else flow_name, waiting)
	return {"title": card["title"], "facts": card["facts"], "note": card["note"], "test_note": card["test_note"]}


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


MAX_DETAILS = 6


def _ref_labels(definition) -> dict:
	"""``{field name: label}`` from the flow's declared input (``contract.input_schema.properties[*].title``)."""
	props = (((definition or {}).get("contract") or {}).get("input_schema") or {}).get("properties")
	return {k: v["title"] for k, v in (props or {}).items() if isinstance(v, dict) and v.get("title")} if isinstance(props, dict) else {}


def _label_of_ref(value, labels: dict) -> str:
	"""A reader's name for ``{"$from": "trigger.address.city"}``: ``City`` (the field), or the step's own name for a whole step."""
	ref = value.get("$from") if isinstance(value, dict) else None
	if not isinstance(ref, str) or not ref:
		return ""
	parts = [p for p in ref.replace("[", ".").replace("]", "").split(".") if p]
	if parts[:1] == ["foreach"]:
		parts = parts[2:] or ["item"]
	elif len(parts) > 1:
		parts = parts[1:]
	path = tuple(p for p in parts if not p.isdigit()) or (parts[0] if parts else "",)
	return humanize._fact_label(path, labels)


def details_facts(details, ctx, labels: dict | None = None) -> list[dict]:
	"""The facts an author chose to show (``[{"label"?, "value": {"$from": ...}}]``): label, then the value as a person reads it.

	A value that does not resolve or is empty is left out (a card never shows a blank row or a raw reference). At most
	``MAX_DETAILS`` rows.
	"""
	labels = labels or {}
	facts: list[dict] = []
	for item in details if isinstance(details, list) else []:
		if not isinstance(item, dict) or len(facts) >= MAX_DETAILS:
			continue
		try:
			value = ctx.resolve(item.get("value"))
		except Exception:
			continue
		text = humanize.summarize(value, labels)
		label = (item.get("label") or "").strip() or _label_of_ref(item.get("value"), labels)
		if text and label:
			facts.append({"label": label, "value": text})
	return facts


def waiting_fields(flow_run, node: dict, rendered_message: str, payload: dict, config: dict | None = None, ctx=None, definition: dict | None = None) -> dict:
	"""What the engine stores on ``waiting`` so every channel can show the same card (message sentence, title, facts)."""
	from huf.ai.graph.error_copy import step_title

	name = flow_name_of(flow_run)
	config = config or {}
	labels = _ref_labels(definition)
	if config.get("details") and ctx is not None:
		facts = details_facts(config["details"], ctx, labels)
	else:
		facts = humanize.key_facts(payload, labels)
	title = ""
	if config.get("title") and ctx is not None:
		from huf.ai.flow.support.router_text import render_text_refs

		title = " ".join(render_text_refs(config["title"], ctx).split())
	return {
		"message": humanize.approval_lead(name, rendered_message),
		"headline": title or humanize.approval_headline(name),
		"title": title or None,
		"flow_name": name,
		"step_title": step_title(node),
		"facts": facts,
		"context_summary": humanize.facts_sentence(facts),
	}
