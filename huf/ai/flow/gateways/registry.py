"""Gateway trigger registry: the per-channel form (``params``) and data (``payload_fields``) of the chat trigger nodes.

One shared node shape ``{gateway, params:[{key, value}]}`` serves ``trigger.gateway``, ``trigger.whatsapp`` and
``trigger.telegram``. Definitions (label, type, options) are never stored in a flow; this module serves them, so a new
channel adds a spec here and no schema or frontend code. Pure Python, no frappe.

Spec shape (frozen by ``tests/test_registry_snapshot.py``; changing it needs coordinator approval)::

    {provider, label, node_type, event_kinds:[{value,label}],
    params:[{key,label,help,type,options:[{value,label}],required,default,multiple,show_when,section}],
    payload_fields:[{path,label,type,sample,customer_provided,sensitive,advanced}],
    sample_payload:{...}}
"""

from __future__ import annotations

from huf.ai.flow.gateways import generic, telegram, whatsapp
from huf.ai.flow.gateways.spec_kit import LIST_TYPES, STRING_TYPES, option, sample_payload

REGISTRY_VERSION = 1
GENERIC_NODE_TYPE = "trigger.gateway"
GATEWAY_NODE_TYPES = (GENERIC_NODE_TYPE, whatsapp.NODE_TYPE, telegram.NODE_TYPE)

# Limits on stored values (also pinned in graph_ir.schema.json GatewayParam).
MAX_PARAMS = 40
MAX_LIST_ITEMS = 50
MAX_TEXT = 500
MAX_ITEM_TEXT = 200
MAX_NUMBER = 1_000_000

_DEDICATED = {whatsapp.NODE_TYPE: whatsapp, telegram.NODE_TYPE: telegram}


def provider_for_node_type(node_type: str) -> str | None:
	"""The provider a dedicated node is tied to; None for the generic node."""
	module = _DEDICATED.get(node_type)
	return module.PROVIDER if module else None


def get_gateway_trigger_spec(provider: str | None = None, node_type: str = GENERIC_NODE_TYPE) -> dict:
	"""The spec for one node type. A dedicated node ignores ``provider``; the generic node serves the generic params.

	A provider with no module still works: it gets the generic spec labelled with its own name.
	"""
	module = _DEDICATED.get(node_type)
	if module is None:
		label = provider or "Chat"
		params = generic.generic_params()
		fields = generic.generic_fields()
		kinds = generic.GENERIC_EVENT_KINDS
	else:
		provider, label, kinds = module.PROVIDER, module.LABEL, module.EVENT_KINDS
		params = [p for p in generic.generic_params() if p["key"] not in module.EXCLUDE_GENERIC] + module.params()
		fields = generic.generic_fields() + module.fields()
	fields = list({f["path"]: f for f in fields}.values())
	return {
		"provider": provider or "",
		"label": label,
		"node_type": node_type if module else GENERIC_NODE_TYPE,
		"event_kinds": [option(v, lbl) for v, lbl in kinds],
		"params": params,
		"payload_fields": fields,
		"sample_payload": sample_payload(fields),
	}


def get_registry() -> dict:
	"""Everything the editor needs in one document: one spec per node type."""
	return {
		"version": REGISTRY_VERSION,
		"limits": {
			"max_params": MAX_PARAMS,
			"max_list_items": MAX_LIST_ITEMS,
			"max_text": MAX_TEXT,
			"max_item_text": MAX_ITEM_TEXT,
		},
		"specs": {node_type: get_gateway_trigger_spec(None, node_type) for node_type in GATEWAY_NODE_TYPES},
	}


# -- value checks (publish time; drafts keep whatever was typed) ---------------------------------------------


def _is_number(value) -> bool:
	return isinstance(value, (int, float)) and not isinstance(value, bool)


def _value_problem(spec_param: dict, value) -> str | None:
	"""A plain sentence when ``value`` is the wrong type, too long or not one of the options; None when fine."""
	label, kind = spec_param["label"], spec_param["type"]
	if value is None:
		return None
	allowed = {o["value"] for o in spec_param["options"]}
	if kind in STRING_TYPES:
		if not isinstance(value, str):
			return f"'{label}' must be text."
		if len(value) > MAX_TEXT:
			return f"'{label}' is too long (at most {MAX_TEXT} characters)."
		if kind == "select" and value and value not in allowed:
			return f"'{label}' has a choice that is not available."
	elif kind in LIST_TYPES:
		if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
			return f"'{label}' must be a list of words."
		if len(value) > MAX_LIST_ITEMS:
			return f"'{label}' can have at most {MAX_LIST_ITEMS} entries."
		if any(len(v) > MAX_ITEM_TEXT for v in value):
			return f"An entry in '{label}' is too long (at most {MAX_ITEM_TEXT} characters)."
		if kind == "multiselect" and any(v not in allowed for v in value):
			return f"'{label}' has a choice that is not available."
	elif kind == "boolean":
		if not isinstance(value, bool):
			return f"'{label}' must be on or off."
	elif kind == "number":
		if not _is_number(value) or not 0 <= value <= MAX_NUMBER:
			return f"'{label}' must be a number between 0 and {MAX_NUMBER}."
	return None


def param_problems(node_type: str, params, provider: str | None = None) -> list[str]:
	"""Plain-sentence problems with a node's ``params`` list: unknown or repeated keys, wrong value types, bad choices."""
	spec = get_gateway_trigger_spec(provider, node_type)
	by_key = {p["key"]: p for p in spec["params"]}
	problems: list[str] = []
	if params is None:
		params = []
	if not isinstance(params, list):
		return ["The options of this trigger are not in the expected form."]
	if len(params) > MAX_PARAMS:
		problems.append(f"This trigger has too many options (at most {MAX_PARAMS}).")
	seen: set[str] = set()
	for item in params:
		key = item.get("key") if isinstance(item, dict) else None
		if key not in by_key:
			problems.append(f"'{key}' is not an option of this trigger.")
			continue
		if key in seen and not by_key[key]["multiple"]:
			problems.append(f"'{by_key[key]['label']}' is set more than once.")
		seen.add(key)
		issue = _value_problem(by_key[key], item.get("value"))
		if issue:
			problems.append(issue)
	for spec_param in by_key.values():
		if spec_param["required"] and spec_param["key"] not in seen:
			problems.append(f"'{spec_param['label']}' is required.")
	return problems


def gateway_trigger_problems(defn: dict, provider_lookup=None) -> list[str]:
	"""Publish-time problems for every chat trigger node in ``defn``.

	``provider_lookup(gateway_name) -> provider | None`` lets the server name the generic node's channel; without it the
	generic spec is used. A blank gateway is reported by the required-config rule, not here.
	"""
	problems: list[str] = []
	for node in defn.get("nodes") or []:
		node_type = node.get("type") if isinstance(node, dict) else None
		if node_type not in GATEWAY_NODE_TYPES:
			continue
		config = node.get("config") or {}
		provider = provider_lookup(config.get("gateway")) if provider_lookup and config.get("gateway") else None
		problems += [f"node {node.get('id')!r} ({node_type}): {p}" for p in param_problems(node_type, config.get("params"), provider)]
	return problems
