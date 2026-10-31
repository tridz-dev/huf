"""The data picker's fields for a chat trigger: the registry's ``payload_fields`` as friendly, ready-to-use entries.

Hidden (``advanced``) fields are left out of the plain list; customer-provided ones are flagged so the editor can warn
when they feed an AI step. Names and examples come from the registry, never from a real message.
"""

from __future__ import annotations

from huf.ai.flow.catalog import fields as cat
from huf.ai.flow.gateways.registry import GATEWAY_NODE_TYPES, get_gateway_trigger_spec


def is_gateway_trigger(node: dict) -> bool:
	return isinstance(node, dict) and node.get("type") in GATEWAY_NODE_TYPES


def kind_of(node_type: str) -> str:
	return node_type.split(".", 1)[1]


def trigger_fields(node: dict, provider: str | None = None) -> list[dict]:
	"""Picker fields (``{path, label, type, sample, customer_provided, sensitive, advanced}``) for a chat trigger node."""
	spec = get_gateway_trigger_spec(provider, node.get("type"))
	out = []
	for item in spec["payload_fields"]:
		sample = item.get("sample")
		out.append(
			{
				"path": item["path"],
				"label": item["label"],
				"type": cat.value_type(sample) if sample is not None else {"yes_no": "yes_no", "list": "list", "record": "object"}.get(item["type"], "text"),
				"sample": cat.sample_for(sample) if sample is not None else None,
				"customer_provided": bool(item.get("customer_provided")),
				"sensitive": bool(item.get("sensitive")),
				"advanced": bool(item.get("advanced")),
			}
		)
	return out
