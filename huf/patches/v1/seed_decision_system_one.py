# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Seed the System One decision stack: provider, classes, families, model,
AI Model row, one disabled default deployment, and a handful of disabled,
Draft sample policies (H2).

This is the reference seed for the Decision Runtime (decision D1/D2/D3, D14,
D16): every row it creates is disabled or Draft, and it creates no Agent
Decision Binding, so nothing changes behavior for an existing site until a
user opts in.

`seed_decision_system_one()` is called from both this patch's `execute()`
(post_model_sync, after `retire_decision_provider`) and from
`huf.install.after_install()`, so a fresh install and a migrated site end up
with the same rows. Every upsert is keyed by the DocType's own key field
(`provider_name`, `class_key`, `family_key`, `model_key`, `model_name`,
`deployment_key`, `policy_name`) and only inserts when the key is absent, so
running it any number of times creates no duplicates.
"""

from __future__ import annotations

import json

import frappe

from huf.ai.decision.catalog import get_entry


PROVIDER_BRAND = "opencode-zen"
CATALOG_MODEL_NAME = "jev-1.13-free"

# Decision Model Class rows (class_key -> display name).
CLASSES = [
	("system_one", "System One"),
	("structured_llm", "Structured LLM"),
	("rules", "Rules"),
	("classifier", "Classifier"),
	("similarity", "Similarity"),
]

# Decision Model Family rows: family_key -> (family_name, adapter_id, model_class key).
FAMILIES = [
	("jev", "Jev", "jev_system_one", "system_one"),
	("local_rules", "Local Rules", "local_rules", "rules"),
	("classifier", "Classifier", "classifier", "classifier"),
	("similarity", "Similarity", "similarity", "similarity"),
	("structured_llm", "Structured LLM", "structured_llm", "structured_llm"),
]

DECISION_MODEL_KEY = "jev-1-13"
DECISION_MODEL_NAME = "Jev 1.13"

DEPLOYMENT_KEY = "jev-1-13-opencode-zen"
DEPLOYMENT_NAME = "Jev 1.13 @ OpenCode Zen"


def _get_or_create(
	doctype: str, key_field: str, key_value: str, values: dict, *, ignore_validate: bool = False
) -> str:
	"""Insert `doctype` keyed by `key_field` if it does not already exist.

	Returns the (existing or newly created) document name. Never updates an
	existing row -- the seed only ever creates, so reruns are pure no-ops.

	`ignore_validate` mirrors the pattern already used by
	`install.create_demo_ai_providers()` for keyless provider rows: this seed
	deliberately creates an `AI Provider` with no `api_key` (D2/D16 -- the key
	is added later by whoever enables the deployment), which
	`AIProvider.validate_api_key()` would otherwise reject.
	"""
	existing = frappe.db.exists(doctype, {key_field: key_value})
	if existing:
		return existing if isinstance(existing, str) else key_value

	payload = {"doctype": doctype, key_field: key_value}
	payload.update(values)
	doc = frappe.get_doc(payload)
	if ignore_validate:
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	return doc.name


# AI Provider.validate_provider_name() rejects whitespace in a new provider_name
# (it becomes the LiteLLM model routing prefix <provider>/<model>), so the seeded
# provider is the single-word "OpenCodeZen" rather than the display spelling
# "OpenCode Zen" used elsewhere (catalog entries, docs, test fixtures).
PROVIDER_NAME = "OpenCodeZen"


def _seed_provider() -> str:
	"""AI Provider 'OpenCodeZen' (brand opencode-zen, no key) if absent."""
	base_url = None
	entry = get_entry(PROVIDER_BRAND, CATALOG_MODEL_NAME)
	if entry is not None:
		base_url = entry.base_url

	return _get_or_create(
		"AI Provider",
		"provider_name",
		PROVIDER_NAME,
		{
			"provider_brand": PROVIDER_BRAND,
			"api_key": "",
			"api_base_url": base_url,
		},
		ignore_validate=True,
	)


def _seed_classes() -> dict:
	"""Decision Model Class rows. Returns class_key -> name."""
	names = {}
	for class_key, class_name in CLASSES:
		names[class_key] = _get_or_create(
			"Decision Model Class",
			"class_key",
			class_key,
			{
				"class_name": class_name,
				"description": f"{class_name} decision models.",
				"enabled": 1,
			},
		)
	return names


def _seed_families(class_names: dict) -> dict:
	"""Decision Model Family rows. Returns family_key -> name."""
	names = {}
	for family_key, family_name, adapter_id, class_key in FAMILIES:
		names[family_key] = _get_or_create(
			"Decision Model Family",
			"family_key",
			family_key,
			{
				"family_name": family_name,
				"adapter_id": adapter_id,
				"model_class": class_names[class_key],
				"description": f"{family_name} decision model family (adapter '{adapter_id}').",
				"enabled": 1,
			},
		)
	return names


def _seed_model(family_names: dict) -> str:
	"""Decision Model 'Jev 1.13'."""
	return _get_or_create(
		"Decision Model",
		"model_key",
		DECISION_MODEL_KEY,
		{
			"model_name": DECISION_MODEL_NAME,
			"family": family_names["jev"],
			"canonical_version": "1.13",
			"display_name": DECISION_MODEL_NAME,
			"enabled": 1,
		},
	)


def _seed_ai_model(provider_name: str) -> str:
	"""AI Model row for the catalog entry (modality Decision)."""
	return _get_or_create(
		"AI Model",
		"model_name",
		CATALOG_MODEL_NAME,
		{
			"provider": provider_name,
			"modalities": "Decision",
		},
	)


def _seed_deployment(decision_model_name: str, ai_model_name: str, provider_name: str) -> str:
	"""Deployment 'Jev 1.13 @ OpenCode Zen': priority 10, default for the
	model, seeded disabled. Label is neutral (no tier wording, D16)."""
	entry = get_entry(PROVIDER_BRAND, CATALOG_MODEL_NAME)
	wire_protocol = entry.wire_protocol if entry else "systemone"
	endpoint_path = entry.endpoint_path if entry else "/v1/systemone"

	return _get_or_create(
		"Decision Deployment",
		"deployment_key",
		DEPLOYMENT_KEY,
		{
			"deployment_name": DEPLOYMENT_NAME,
			"decision_model": decision_model_name,
			"ai_model": ai_model_name,
			# provider / provider_model_id are fetch_from(ai_model.*) read-only fields;
			# set explicitly too so the seed is correct even if fetch_from does not run
			# on a server-side insert.
			"provider": provider_name,
			"provider_model_id": CATALOG_MODEL_NAME,
			"wire_protocol": wire_protocol,
			"endpoint_path": endpoint_path,
			"priority": 10,
			"is_default_for_model": 1,
			"enabled": 0,
		},
	)


# Sample policies (H2): Draft (no published version) and disabled. None of
# these create an Agent Decision Binding, so they change nothing by
# themselves -- they exist as ready-to-publish starting points.
def _policy_definition(policy_id: str, question: dict) -> str:
	# Every policy must explicitly bind at least one piece of provider-visible state
	# (huf.ai.decision.state.prepare_state) or it can be published but never actually run.
	# Sample policies bind the whole caller-supplied state under "request"; a real policy
	# built in the Decisions editor will usually bind narrower, named fields instead.
	return json.dumps(
		{
			"policy_id": policy_id,
			"questions": [question],
			"state_bindings": [{"name": "request", "path": "request"}],
		}
	)


SAMPLE_POLICIES = [
	{
		"policy_name": "Support Urgency",
		"purpose": "Generic",
		"description": "Judge whether an incoming support request needs immediate escalation.",
		"definition": _policy_definition(
			"support_urgency",
			{
				"id": "is_urgent",
				"kind": "judge",
				"instructions": (
					"Judge whether this support request is urgent enough to escalate immediately."
				),
				"positive_criteria": (
					"Customer reports a service outage, data loss, a security issue, or is blocked "
					"from critical work."
				),
				"negative_criteria": (
					"General question, feature request, or a minor cosmetic issue."
				),
			},
		),
	},
	{
		"policy_name": "Default Tool Relevance",
		"purpose": "Tool Selection",
		"description": "Select whether a candidate tool is relevant to the user's request.",
		"definition": _policy_definition(
			"default_tool_relevance",
			{
				"id": "relevance",
				"kind": "select",
				"instructions": "Select whether the candidate tool is relevant to fulfilling the user's request.",
				"options": [
					{"id": "relevant", "description": "The tool is relevant to the request."},
					{"id": "not_relevant", "description": "The tool is not relevant to the request."},
				],
			},
		),
	},
	{
		"policy_name": "Default Skill Fit",
		"purpose": "Skill Selection",
		"description": "Select whether a candidate skill fits the current task.",
		"definition": _policy_definition(
			"default_skill_fit",
			{
				"id": "fit",
				"kind": "select",
				"instructions": "Select whether the candidate skill fits the current task.",
				"options": [
					{"id": "fits", "description": "The skill matches the current task."},
					{"id": "does_not_fit", "description": "The skill does not match the current task."},
				],
			},
		),
	},
	{
		"policy_name": "Default Flow Route",
		"purpose": "Flow Routing",
		"description": "Select which flow branch to continue on for a closed set of routes.",
		"definition": _policy_definition(
			"default_flow_route",
			{
				"id": "route",
				"kind": "select",
				"instructions": "Select which branch this run should continue on.",
				"options": [
					{"id": "continue", "description": "Continue on the default path."},
					{"id": "escalate", "description": "Route to the escalation path."},
				],
			},
		),
	},
	{
		"policy_name": "Issue Priority",
		"purpose": "Generic",
		"description": (
			"Score an issue's priority on a fixed rubric. Simple enough for the local_rules backend."
		),
		"definition": _policy_definition(
			"issue_priority",
			{
				"id": "priority",
				"kind": "score",
				"instructions": "Score the priority of this issue against the rubric levels below.",
				"options": [
					{"id": "low", "description": "No user impact; can wait."},
					{"id": "medium", "description": "Limited impact; schedule normally."},
					{"id": "high", "description": "Significant impact; prioritize soon."},
					{"id": "critical", "description": "Severe impact; handle immediately."},
				],
			},
		),
	},
]


def _seed_sample_policies() -> list:
	from huf.ai.decision.policy import validate_policy_data

	created = []
	for policy in SAMPLE_POLICIES:
		# Validate before insert so a bad definition never lands on disk half-seeded.
		validate_policy_data(json.loads(policy["definition"]))
		name = _get_or_create(
			"Decision Policy",
			"policy_name",
			policy["policy_name"],
			{
				"purpose": policy["purpose"],
				"description": policy["description"],
				"definition_json": policy["definition"],
				"schema_version": "1.0",
				"enabled": 0,
			},
		)
		created.append(name)
	return created


def seed_decision_system_one() -> None:
	"""Idempotently seed the System One decision stack. Safe to call any
	number of times, from a patch or from after_install.

	Raises on failure -- callers that must not fail on a seed error (e.g.
	after_install) are responsible for their own try/except + log_error, so
	a real bug in a patch run (`bench migrate`) still surfaces loudly."""
	provider_name = _seed_provider()
	class_names = _seed_classes()
	family_names = _seed_families(class_names)
	decision_model_name = _seed_model(family_names)
	ai_model_name = _seed_ai_model(provider_name)
	_seed_deployment(decision_model_name, ai_model_name, provider_name)
	_seed_sample_policies()
	frappe.db.commit()


def execute() -> None:
	seed_decision_system_one()
