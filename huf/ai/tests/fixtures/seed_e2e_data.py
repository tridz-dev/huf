# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Idempotent fixture seeding for the Playwright e2e CI job
(.github/workflows/e2e-tests.yml).

Invoked from the workflow as:

    bench --site <site> execute huf.ai.tests.fixtures.seed_e2e_data.seed

Environment variables (all optional except the API key, which has a
placeholder fallback so seeding never fails when the GitHub secret
E2E_LLM_PROVIDER_API_KEY is not configured):

    E2E_LLM_PROVIDER_API_KEY  API key stored on the AI Provider doc.
    E2E_PROVIDER_NAME         AI Provider doc name (default "E2E OpenAI").
    E2E_LLM_MODEL             AI Model name     (default "openai/gpt-4o-mini").
    E2E_TEST_AGENT            Agent name        (default "Test New UI").

What gets seeded:

    1. Agent Tool Type    "E2E Tools"            (required link on tools)
    2. AI Provider        openai brand + api_key from env
    3. AI Model           linked to the provider
    4. Agent Tool Function  "list_agents_e2e"    (Get List on "Agent" —
        self-referential and read-only; params/function_definition are
        computed automatically in AgentToolFunction.before_save)
    5. Agent              E2E_TEST_AGENT with allow_chat=1 and
        persist_conversation=1 (Agent.validate() rejects allow_chat
        without persist_conversation), instructions, and the tool above
        linked via the agent_tool child table.

Re-running is safe: every document is upserted via frappe.db.exists.
"""

import os

import frappe

PLACEHOLDER_API_KEY = "sk-e2e-placeholder-no-secret-configured"
TOOL_TYPE_NAME = "E2E Tools"
TOOL_NAME = "list_agents_e2e"


def _env(name, default):
	value = os.environ.get(name)
	return value if value else default


def seed():
	frappe.set_user("Administrator")

	provider_name = _env("E2E_PROVIDER_NAME", "E2E OpenAI")
	model_name = _env("E2E_LLM_MODEL", "openai/gpt-4o-mini")
	api_key = os.environ.get("E2E_LLM_PROVIDER_API_KEY") or PLACEHOLDER_API_KEY
	agent_name = _env("E2E_TEST_AGENT", "Test New UI")

	if api_key == PLACEHOLDER_API_KEY:
		print(
			"[seed_e2e_data] WARNING: E2E_LLM_PROVIDER_API_KEY is not set; "
			"seeding a placeholder key. Specs that need a real LLM response "
			"(chat response, tool-call flow) will fail until the "
			"E2E_LLM_PROVIDER_API_KEY repository secret is configured."
		)

	_seed_tool_type()
	_seed_provider(provider_name, api_key)
	_seed_model(model_name, provider_name)
	_seed_tool_function()
	_seed_agent(agent_name, provider_name, model_name)

	frappe.db.commit()
	print(
		f"[seed_e2e_data] done: provider={provider_name!r} model={model_name!r} "
		f"agent={agent_name!r} tool={TOOL_NAME!r}"
	)


def _seed_tool_type():
	if frappe.db.exists("Agent Tool Type", TOOL_TYPE_NAME):
		return
	frappe.get_doc({"doctype": "Agent Tool Type", "name1": TOOL_TYPE_NAME}).insert(
		ignore_permissions=True
	)


def _seed_provider(provider_name, api_key):
	if frappe.db.exists("AI Provider", provider_name):
		doc = frappe.get_doc("AI Provider", provider_name)
	else:
		doc = frappe.new_doc("AI Provider")
		doc.provider_name = provider_name
	doc.provider_brand = "openai"
	doc.api_key = api_key  # Password field — refreshed on every run (key rotation)
	doc.save(ignore_permissions=True)


def _seed_model(model_name, provider_name):
	if frappe.db.exists("AI Model", model_name):
		doc = frappe.get_doc("AI Model", model_name)
	else:
		doc = frappe.new_doc("AI Model")
		doc.model_name = model_name
	doc.provider = provider_name
	doc.save(ignore_permissions=True)


def _seed_tool_function():
	if frappe.db.exists("Agent Tool Function", TOOL_NAME):
		doc = frappe.get_doc("Agent Tool Function", TOOL_NAME)
	else:
		doc = frappe.new_doc("Agent Tool Function")
		doc.tool_name = TOOL_NAME
	doc.description = "List Agent documents. Safe read-only tool used by e2e fixtures."
	doc.types = "Get List"
	doc.reference_doctype = "Agent"
	doc.tool_type = TOOL_TYPE_NAME
	doc.is_read_only = 1
	# before_save computes `params` and `function_definition` from the fields above.
	doc.save(ignore_permissions=True)


def _seed_agent(agent_name, provider_name, model_name):
	if frappe.db.exists("Agent", agent_name):
		doc = frappe.get_doc("Agent", agent_name)
	else:
		doc = frappe.new_doc("Agent")
		doc.agent_name = agent_name

	doc.provider = provider_name
	doc.model = model_name
	doc.instructions = (
		"You are a concise test agent used by the e2e suite. "
		"Answer briefly. When asked to list records, use the list_agents_e2e tool."
	)
	# Agent.validate() throws when allow_chat=1 and persist_conversation=0.
	doc.allow_chat = 1
	doc.persist_conversation = 1
	doc.disabled = 0

	if not any(row.tool == TOOL_NAME for row in doc.get("agent_tool") or []):
		doc.append("agent_tool", {"tool": TOOL_NAME})

	doc.save(ignore_permissions=True)
