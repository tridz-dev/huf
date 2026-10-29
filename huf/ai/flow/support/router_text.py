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
			raise RuntimeError(f"AI model '{model_name}' was not found")
		if not _provider_has_key(provider):
			raise RuntimeError(f"AI provider '{provider}' for model '{model_name}' has no API key")
		return provider, model_name

	provider = _find_keyed_provider()
	model = _default_model_for_provider(provider) if provider else None
	if not provider or not model:
		raise RuntimeError("no AI Provider with an API key and a chat model is configured")
	return provider, model


def _router_completion(prompt_text: str, provider: str, model: str) -> str:
	"""One direct LLM completion (no agent involved) with the given provider and model."""
	from huf.ai.providers.litellm import get_simple_completion

	return _run_coroutine(get_simple_completion(model, [{"role": "user", "content": prompt_text}], provider))


_TEXT_REF_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)\}(?!\})")


def render_text_refs(text: str, ctx: GraphContext) -> str:
	"""Fill ``{input.field}`` / ``{node_id.field}`` / ``{foreach.item}`` placeholders in a plain-text field.

	Used for ``router.llm.prompt`` and ``human.approval.message`` (the Insert data picker writes these).
	A placeholder that does not resolve is left as written, so ordinary braces in a message never fail a run.
	"""
	from huf.ai.graph.templates import _stringify

	def sub(match: re.Match) -> str:
		path = match.group(1)
		if path.split(".")[0].split("[")[0] not in ctx.reference_roots():
			return match.group(0)
		value = ctx.resolve_reference(path)
		return match.group(0) if value is None else _stringify(value)

	return _TEXT_REF_RE.sub(sub, text or "")
