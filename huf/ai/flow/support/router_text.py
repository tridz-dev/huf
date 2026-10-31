"""Text helpers for the LLM Router and for placeholder rendering in plain-text step fields.

Split out of ``engine.py``. The engine imports these names and calls them through its own globals, so
tests can still patch ``resolve_router_model`` / ``_router_completion`` on the engine module.
"""

from __future__ import annotations

import json
import re

import frappe

from huf.ai.graph.executor import GraphContext


def build_router_llm_prompt(prompt: str, options: list, context: dict) -> str:
	"""Prompt asking the model to pick exactly one option label."""
	labels = [str((o or {}).get("label")) for o in options]
	return "\n".join(
		[
			"You are a routing step in a workflow. Choose exactly one option for the situation below.",
			"Reply with ONLY the option label, exactly as written, and nothing else.",
			"",
			"## Instruction",
			str(prompt),
			"",
			"## Options",
			*[f"- {label}" for label in labels],
			"",
			"## Workflow input",
			json.dumps(context, default=str)[:4000],
		]
	)


def choose_option(text: str, options: list) -> dict | None:
	"""Map the model's reply onto one option (``{"label", "node_id"}``), or None.

	Accepts the bare label, a quoted label, a JSON object with ``label``, or a reply that mentions
	exactly one label. Ambiguity or no match is None (the caller routes to ``default``).
	"""
	if not isinstance(text, str) or not text.strip():
		return None
	by_label = {str((o or {}).get("label", "")).strip().lower(): o for o in options if (o or {}).get("node_id")}
	candidate = text.strip().strip("`\"' \n.")
	if candidate.startswith("{"):
		try:
			parsed = json.loads(text.strip().strip("`"))
			if isinstance(parsed, dict):
				candidate = str(parsed.get("label", "")).strip()
		except ValueError:
			pass
	if candidate.lower() in by_label:
		return by_label[candidate.lower()]
	lowered = text.lower()
	hits = [o for label, o in by_label.items() if label and label in lowered]
	return hits[0] if len(hits) == 1 else None


def _run_coroutine(coro):
	import asyncio

	loop = asyncio.new_event_loop()
	try:
		return loop.run_until_complete(coro)
	finally:
		loop.close()


def resolve_router_model(model_name: str | None = None) -> tuple[str, str]:
	"""``(provider, model)`` for a router step.

	``model_name`` is the name of an AI Model record: its provider is used. Without one, the first
	keyed provider's default chat model is used. A named model that is missing, or whose provider has
	no API key, is an authoring error and raises (the router then routes to its default).
	"""
	from huf.ai.app_seeding.hub_orchestrator import (
		_default_model_for_provider,
		_find_keyed_provider,
		_provider_has_key,
	)

	if model_name:
		provider = frappe.db.get_value("AI Model", model_name, "provider")
		if not provider:
			raise RuntimeError(f"The AI model \"{model_name}\" was not found. Pick another model in this step.")
		if not _provider_has_key(provider):
			raise RuntimeError(f"{provider} has no API key yet. Add one in AI Providers.")
		return provider, model_name

	provider = _find_keyed_provider()
	model = _default_model_for_provider(provider) if provider else None
	if not provider or not model:
		raise RuntimeError("No AI provider is set up yet. Add one with its API key in AI Providers.")
	return provider, model


def _router_completion(prompt_text: str, provider: str, model: str) -> str:
	"""One direct LLM completion (no agent involved) with the given provider and model."""
	from huf.ai.providers.litellm import get_simple_completion

	return _run_coroutine(get_simple_completion(model, [{"role": "user", "content": prompt_text}], provider))


# ``{input.total}``; ``{table:input.order}`` / ``{joined:n1.items}`` / ``{count:n1.items}`` ask for a record as rows, a list
# joined with commas, or the number of items (the same three wordings "Use data" offers in a template).
_TEXT_REF_RE = re.compile(
	r"(?<!\{)\{(?:(table|joined|count):)?([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)\}(?!\})"
)

# Roots that always exist; every step id is also a root.
_FIXED_REF_ROOTS = ("input", "trigger", "context", "foreach")


def render_text_refs(text: str, ctx: GraphContext) -> str:
	"""Fill ``{input.field}`` / ``{node_id.field}`` / ``{foreach.item}`` placeholders in a plain-text field.

	Used for ``router.llm.prompt`` and ``human.approval.message`` (the Insert data picker writes these), text
	that people read. A value is written the way a person reads it (:func:`humanize.summarize`): a whole
	object or list becomes a short summary, never JSON, and a date reads as a date. A placeholder that does not
	resolve renders as an empty value, never as the literal braces (the flow author gets a warning when the flow
	is saved, see :func:`text_ref_warnings`), so a message never fails a run and never shows ``{input.x}``.
	"""
	from huf.ai.flow.support.humanize import summarize
	from huf.ai.graph.templates import render_marked

	def sub(match: re.Match) -> str:
		mode, path = match.group(1), match.group(2)
		if path.split(".")[0].split("[")[0] not in ctx.reference_roots():
			return ""
		value = ctx.resolve_reference(path)
		marked = render_marked(mode, value) if mode else None
		return marked if marked is not None else (summarize(value) or "")

	return _TEXT_REF_RE.sub(sub, text or "")


# Plain-text step fields that take {placeholders}, by step type, with the name people see for the field.
_TEXT_REF_FIELDS = {"human.approval": (("message", "message"), ("title", "title")), "router.llm": (("prompt", "instruction"),)}


def text_ref_warnings(defn: dict | None) -> list[str]:
	"""Plain sentences for placeholders in message/prompt fields that point at nothing, for the save response.

	A placeholder whose first part is neither the trigger input nor a step of this flow renders as an empty
	value; this says so at save time, naming the step the way the canvas does.
	"""
	from huf.ai.graph.error_copy import step_title

	nodes = (defn or {}).get("nodes") if isinstance(defn, dict) else None
	if isinstance(nodes, dict):
		nodes = [{"id": k, **(v or {})} for k, v in nodes.items()]
	nodes = [n for n in (nodes or []) if isinstance(n, dict)]
	roots = set(_FIXED_REF_ROOTS) | {str(n.get("id")) for n in nodes if n.get("id")}
	warnings: list[str] = []
	for node in nodes:
		for field, noun in _TEXT_REF_FIELDS.get(str(node.get("type")), ()):
			text = (node.get("config") or {}).get(field)
			if not isinstance(text, str):
				continue
			bad = []
			for match in _TEXT_REF_RE.finditer(text):
				path = match.group(2)
				if path.split(".")[0].split("[")[0] not in roots and match.group(0) not in bad:
					bad.append(match.group(0))
			if bad:
				warnings.append(
					f'{step_title(node)}: the {noun} uses {", ".join(bad)}, which has no data behind it, so it will be '
					"left empty. Insert data from an earlier step instead."
				)
	return warnings


def text_ref_warnings_for(definition_json) -> list[str]:
	""":func:`text_ref_warnings` for a definition given as JSON text or a dict; unreadable input has no warnings."""
	import json

	try:
		return text_ref_warnings(json.loads(definition_json) if isinstance(definition_json, str) else definition_json)
	except (ValueError, TypeError):
		return []
