# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Whitelisted API methods for the Console prompt-engineering workspace.

Provides:
- Prompt generation from a natural-language description.
- Pass/fail evaluation of a model response against criteria.
- Saving an arbitrary prompt body as an Agent Prompt template.
"""

import asyncio
import json
import re

import frappe
from frappe import _
from frappe.utils import cint

from huf.ai.agent_integration import _run_async_safely
from huf.ai.providers.litellm import get_simple_completion
from huf.permissions import has_capability


GENERATE_PROMPT_CAPABILITY = "agent.use"
EVALUATE_RUN_CAPABILITY = "agent.use"
SAVE_PROMPT_TEMPLATE_CAPABILITY = "agent.create"


def _require(capability: str) -> None:
	"""Throw a PermissionError if the current user lacks *capability*."""
	if not has_capability(frappe.session.user, capability):
		frappe.throw(
			_("You don't have permission to perform this action."),
			frappe.PermissionError,
		)


def _get_console_model_config() -> tuple[str | None, str | None]:
	"""Return (provider, model) to use for console helper calls.

	Priority:
	1. Site config ``huf_console_prompt_engineer_model`` as ``provider:model``.
	2. First enabled AI Provider that has an API key, paired with its first model.
	"""
	configured = frappe.conf.get("huf_console_prompt_engineer_model")
	if configured and isinstance(configured, str) and ":" in configured:
		provider, model = configured.split(":", 1)
		if frappe.db.exists("AI Provider", provider) and frappe.db.exists("AI Model", model):
			return provider.strip(), model.strip()

	providers = frappe.get_all(
		"AI Provider",
		fields=["name", "provider_brand"],
		order_by="modified desc",
	)
	for provider in providers:
		provider_name = provider.get("name") if isinstance(provider, dict) else getattr(provider, "name", None)
		if not provider_name:
			continue
		try:
			doc = frappe.get_doc("AI Provider", provider_name)
			if doc.get_password("api_key"):
				model = frappe.db.get_value(
					"AI Model",
					{"provider": provider_name},
					"name",
					order_by="modified desc",
				)
				if model:
					return provider_name, model
		except Exception:
			continue

	return None, None


def _simple_completion_sync(provider: str, model: str, messages: list) -> str:
	"""Run the async get_simple_completion helper safely in a sync Frappe context."""
	return _run_async_safely(get_simple_completion(model, messages, provider))


@frappe.whitelist()
def generate_prompt(
	description: str,
	tone: str | None = None,
	audience: str | None = None,
	constraints: str | None = None,
):
	"""Generate a system-style prompt from a natural-language description.

	Args:
		description: What the prompt should do.
		tone: Optional desired tone (e.g. "professional", "friendly").
		audience: Optional target audience.
		constraints: Optional extra constraints or output format requirements.

	Returns:
		dict: ``{"prompt": "<generated prompt text>"}``
	"""
	_require(GENERATE_PROMPT_CAPABILITY)

	if not description or not description.strip():
		frappe.throw(_("Description is required."), frappe.ValidationError)

	provider, model = _get_console_model_config()
	if not provider or not model:
		frappe.throw(
			_(
				"No AI provider is available for prompt generation. "
				"Configure one with an API key or set 'huf_console_prompt_engineer_model' in site config."
			),
			frappe.ValidationError,
		)

	parts = [
		"You are an expert prompt engineer. Convert the following request into a clear, "
		"well-structured system prompt. The prompt should define the assistant's role, "
		"goals, constraints, and output format where relevant. Return only the final prompt text."
	]
	if tone:
		parts.append(f"Tone: {tone}")
	if audience:
		parts.append(f"Audience: {audience}")
	if constraints:
		parts.append(f"Constraints: {constraints}")

	parts.append(f"Request: {description.strip()}")
	parts.append("Prompt:")

	messages = [{"role": "user", "content": "\n".join(parts)}]

	try:
		generated = _simple_completion_sync(provider, model, messages)
	except Exception as e:
		frappe.log_error(f"generate_prompt failed: {e!s}\n{frappe.get_traceback()}", "Console Prompt Generation")
		frappe.throw(_("Prompt generation failed. Please try again or choose a different provider."))

	if not generated:
		frappe.throw(_("No prompt was generated. Please try again with a different description or provider."))

	return {"prompt": generated.strip()}


@frappe.whitelist()
def evaluate_run(
	response: str,
	criteria: str,
	provider: str | None = None,
	model: str | None = None,
):
	"""Evaluate a model response against user-supplied pass/fail criteria.

	Args:
		response: The model output to evaluate.
		criteria: The criteria the response must satisfy.
		provider: Optional provider to use for evaluation (defaults to console config).
		model: Optional model to use for evaluation (defaults to console config).

	Returns:
		dict: ``{"passed": bool, "score": number, "reasoning": string}``
	"""
	_require(EVALUATE_RUN_CAPABILITY)

	if not response or not response.strip():
		frappe.throw(_("Response is required."), frappe.ValidationError)
	if not criteria or not criteria.strip():
		frappe.throw(_("Criteria are required."), frappe.ValidationError)

	if provider and model:
		if not frappe.db.exists("AI Provider", provider):
			frappe.throw(_("Selected provider does not exist."), frappe.ValidationError)
		if not frappe.db.exists("AI Model", model):
			frappe.throw(_("Selected model does not exist."), frappe.ValidationError)
	else:
		provider, model = _get_console_model_config()
		if not provider or not model:
			frappe.throw(
				_(
					"No AI provider is available for evaluation. "
					"Configure one with an API key or set 'huf_console_prompt_engineer_model' in site config."
				),
				frappe.ValidationError,
			)

	instructions = (
		"You are a strict evaluator. Given a model response and a set of criteria, "
		"decide whether the response passes the criteria. Provide a score from 0 to 100 "
		"and a short reasoning. Respond with ONLY a JSON object in this exact shape:\n"
		'{"passed": true|false, "score": number, "reasoning": "string"}\n\n'
		"Do not include markdown code fences or any other text."
	)
	content = (
		f"Criteria:\n{criteria.strip()}\n\n"
		f"Response:\n{response.strip()}\n\n"
		"Evaluation JSON:"
	)
	messages = [
		{"role": "system", "content": instructions},
		{"role": "user", "content": content},
	]

	try:
		raw = _simple_completion_sync(provider, model, messages)
	except Exception as e:
		frappe.log_error(f"evaluate_run failed: {e!s}\n{frappe.get_traceback()}", "Console Evaluation")
		frappe.throw(_("Evaluation failed. Please try again or choose a different provider."))

	if not raw:
		frappe.throw(_("No evaluation was returned. Please try again."))

	parsed = _parse_evaluation_json(raw)
	return parsed


def _parse_evaluation_json(raw: str) -> dict:
	"""Parse and validate the evaluator JSON response."""
	# Strip markdown fences if the model ignored instructions.
	cleaned = raw.strip()
	if cleaned.startswith("```"):
		cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
		cleaned = re.sub(r"\s*```$", "", cleaned)
		cleaned = cleaned.strip()

	try:
		data = json.loads(cleaned)
	except json.JSONDecodeError as e:
		frappe.log_error(f"evaluate_run JSON parse failed. Raw: {raw!r}", "Console Evaluation")
		frappe.throw(_("Evaluation returned invalid JSON. Please try again."))

	if not isinstance(data, dict):
		frappe.throw(_("Evaluation returned an unexpected format."))

	passed = bool(data.get("passed"))
	score = data.get("score")
	reasoning = data.get("reasoning")

	try:
		score = float(score)
	except (TypeError, ValueError):
		score = 100.0 if passed else 0.0

	score = max(0.0, min(100.0, score))

	if not reasoning or not isinstance(reasoning, str):
		reasoning = "No reasoning provided."

	return {"passed": passed, "score": round(score, 1), "reasoning": reasoning.strip()}


@frappe.whitelist()
def save_prompt_template(
	prompt_body: str,
	title: str,
	description: str | None = None,
	category: str | None = None,
	visibility: str = "Private",
	tags: str | None = None,
):
	"""Save an arbitrary prompt body as a new Agent Prompt template.

	Args:
		prompt_body: The prompt text to save.
		title: Template title.
		description: Optional description.
		category: Optional Agent Prompt Category link.
		visibility: Public / App / Private.
		tags: Optional comma-separated tags.

	Returns:
		dict: ``{"name": "<prompt_name>", "version": 1}``
	"""
	_require(SAVE_PROMPT_TEMPLATE_CAPABILITY)

	if not prompt_body or not prompt_body.strip():
		frappe.throw(_("Prompt body is required."), frappe.ValidationError)
	if not title or not title.strip():
		frappe.throw(_("Title is required."), frappe.ValidationError)

	valid_visibility = {"Public", "App", "Private"}
	if visibility not in valid_visibility:
		visibility = "Private"

	if category and not frappe.db.exists("Agent Prompt Category", category):
		frappe.throw(_("Selected category does not exist."), frappe.ValidationError)

	prompt = frappe.get_doc({
		"doctype": "Agent Prompt",
		"title": title.strip(),
		"description": description.strip() if description else None,
		"category": category or None,
		"prompt_body": prompt_body.strip(),
		"visibility": visibility,
		"is_active": 1,
		"is_system": 0,
		"tags": tags.strip() if tags else None,
		"version": 1,
		"is_latest": 1,
	})
	prompt.insert()

	return {"name": prompt.name, "version": 1}
