"""The data a one-step test starts from, and how a test's output is made safe to show (UX-16).

``build_sample_input`` answers "what does this step receive?" with the data the step actually reads:

* ``input``: what the flow starts with. The trigger's saved sample request (``_sample`` on the trigger) first, else
  the data of the latest successful run.
* one entry per earlier step the step reads from: the sample pinned on that step (``_sample``) first, else what it
  produced in the latest successful run.
* ``item``: the current item, when the step sits inside a loop.

Every value is passed through :func:`redact_output` (secrets hidden, long text and big lists shortened, 64 KB at
most), so what a person sees is exactly what the test runs with. The pure parts need no database.
"""

from __future__ import annotations

import json
import re
from typing import Any

from huf.ai.flow.catalog import fields as cat
from huf.ai.flow.support.trigger_sample import MASK, MAX_SAMPLE_BYTES, redact_sample

MAX_OUTPUT_BYTES = 64 * 1024
MAX_PART_BYTES = 16 * 1024
MAX_DEPTH = 8
_SECRET_KEY = re.compile(r"pass(word|wd)?|secret|token|authorization|api[_-]?key|credential|cookie|signature|private", re.I)
# Values that look like credentials even when the key around them is harmless ("value": "sk-...").
_SECRET_VALUE = re.compile(
	r"(sk-[A-Za-z0-9_\-]{16,}|xox[abprs]-[A-Za-z0-9\-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}"
	r"|Bearer\s+[A-Za-z0-9._\-]{16,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,})"
)

SOURCE_PINNED = "pinned"
SOURCE_TRIGGER_SAMPLE = "trigger_sample"
SOURCE_LAST_RUN = "last_run"
SOURCE_NONE = "none"

INPUT_TITLE = "What the flow starts with"
ITEM_TITLE = "The item being worked on"


# --------------------------------------------------------------------------- redaction


def _shrink(value: Any, depth: int, max_text: int, max_list: int) -> Any:
	if depth > MAX_DEPTH:
		return "..."
	if isinstance(value, dict):
		out = {}
		for i, (key, item) in enumerate(value.items()):
			if i >= 60:
				break
			out[str(key)] = MASK if _SECRET_KEY.search(str(key)) and item not in (None, "") else _shrink(item, depth + 1, max_text, max_list)
		return out
	if isinstance(value, (list, tuple)):
		return [_shrink(item, depth + 1, max_text, max_list) for item in list(value)[:max_list]]
	if isinstance(value, str):
		text = _SECRET_VALUE.sub(MASK, value)
		return text if len(text) <= max_text else text[: max_text - 3] + "..."
	if value is None or isinstance(value, (bool, int, float)):
		return value
	return str(value)[:max_text]


def _size(value: Any) -> int:
	return len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))


def redact_output(value: Any, max_bytes: int = MAX_OUTPUT_BYTES) -> tuple[Any, bool]:
	"""``(safe copy, was_shortened)``: secrets hidden, long text and big lists shortened, at most ``max_bytes`` as JSON."""
	value = json.loads(json.dumps(value, default=str)) if value is not None else None
	shortened = False
	for max_text, max_list in ((4000, 100), (1000, 40), (300, 15), (120, 5)):
		safe = _shrink(value, 0, max_text, max_list)
		if _size(safe) <= max_bytes:
			return safe, safe != value
		shortened = True
	return {"note": "The result is too large to show."}, True


def pin_value(value: Any) -> Any:
	"""What "Pin this output" stores on the step (``_sample``): at most 8 KB, secrets hidden. Objects keep their field names."""
	if isinstance(value, dict):
		return redact_sample(value)
	safe, _ = redact_output(value, MAX_SAMPLE_BYTES)
	return safe


# --------------------------------------------------------------------------- what the step reads


def references(node: dict) -> set[str]:
	"""Words in the step's settings that may name data: ``$from`` roots, ``input``, ``trigger``, step ids in expressions."""
	text = json.dumps(node.get("config") or {}, default=str)
	return set(re.findall(r"[A-Za-z_][A-Za-z0-9_\-]*", text))


def _part(key: str, title: str, kind: str, source: str, value: Any, ran_at: Any = None) -> dict:
	safe, shortened = redact_output(value, MAX_PART_BYTES) if value is not None else (None, False)
	return {"key": key, "title": title, "kind": kind, "source": source, "value": safe, "shortened": shortened, "ran_at": ran_at}


def _trigger_node(graph: dict) -> dict | None:
	nodes = cat.graph_nodes(graph)
	triggers = [n for n in nodes if str(n.get("type", "")).startswith("trigger.")]
	entry = graph.get("entry")
	entry = entry if isinstance(entry, list) else [entry]
	pool = [t for t in triggers if t["id"] in entry] or triggers
	return next((t for t in pool if t.get("_sample") is not None), pool[0] if pool else None)


def build_sample_input(graph: dict, node_id: str, run: dict | None, titles: dict[str, str]) -> dict:
	"""``{"parts": [...], "sample_input": {...}, "notes": [...]}`` for a step.

	``run`` is the latest successful run as ``{"creation", "trigger_payload", "context_json"}`` (or ``None``);
	``titles`` maps step id to the title a person gave it. ``parts`` is for display, ``sample_input`` is what the
	test runs with (and what an edited sample replaces).
	"""
	from huf.ai.flow.catalog.api import _run_outputs, _run_payload

	by_id = {n["id"]: n for n in cat.graph_nodes(graph)}
	node = by_id.get(node_id) or {}
	words = references(node)
	outputs = _run_outputs(run)
	ran_at = str(run["creation"]) if run else None
	parts: list[dict] = []
	steps: dict[str, Any] = {}

	loop_node = cat.enclosing_loop(graph, node_id)
	trigger = _trigger_node(graph)
	trigger_data = None
	if trigger is not None and isinstance(trigger.get("_sample"), dict):
		trigger_data, source = trigger["_sample"], SOURCE_TRIGGER_SAMPLE
		stamp = trigger.get("_sample_at")
	else:
		trigger_data, source, stamp = _run_payload(run), SOURCE_LAST_RUN, ran_at
		if trigger_data is None:
			source = SOURCE_NONE
	if words & {"input", "trigger", "context"} or (loop_node is not None and trigger_data is not None):
		parts.append(_part("input", INPUT_TITLE, "input", source, trigger_data, stamp))

	for pid in sorted(cat.guaranteed_predecessors(graph, node_id)):
		pnode = by_id.get(pid)
		if not pnode or str(pnode.get("type", "")).startswith("trigger.") or pid not in words:
			continue
		pinned = pnode.get("_sample")
		if pinned is not None:
			value, source, stamp = pinned, SOURCE_PINNED, pnode.get("_sample_at")
		elif pid in outputs:
			value, source, stamp = outputs[pid], SOURCE_LAST_RUN, ran_at
		else:
			value, source, stamp = None, SOURCE_NONE, None
		part = _part(pid, titles.get(pid) or pid, "step", source, value, stamp)
		parts.append(part)
		if value is not None:
			steps[pid] = part["value"]

	item = None
	loop = loop_node
	if loop is not None:
		from huf.ai.graph.executor import GraphContext

		ctx = GraphContext(parts[0]["value"] if parts and parts[0]["key"] == "input" and isinstance(parts[0]["value"], dict) else {})
		ctx.node_outputs = dict(steps)
		try:
			items = ctx.resolve((loop.get("config") or {}).get("items"))
		except Exception:
			items = None
		if isinstance(items, list) and items:
			item = items[0]
			parts.append(_part("item", ITEM_TITLE, "item", parts[0]["source"] if parts else SOURCE_NONE, item))

	input_part = next((p for p in parts if p["key"] == "input"), None)
	sample_input: dict = {"input": input_part["value"] if input_part and input_part["value"] is not None else {}, "steps": steps}
	if item is not None:
		sample_input["item"] = parts[-1]["value"]
	return {"parts": parts, "sample_input": sample_input}


def clean_sample_input(raw: Any) -> dict:
	"""A caller-supplied sample, checked: an object with ``input`` (object), ``steps`` (object) and ``item`` (anything), 64 KB at most."""
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			raise ValueError("The sample is not valid JSON.") from None
	if not isinstance(raw, dict):
		raise ValueError("The sample has to be an object with the data this step receives.")
	unknown = sorted(set(raw) - {"input", "steps", "item"})
	if unknown:
		raise ValueError("The sample can only hold input, steps and item.")
	if _size(raw) > MAX_OUTPUT_BYTES:
		raise ValueError("The sample is too large (64 KB at most).")
	data = raw.get("input")
	steps = raw.get("steps")
	if data is not None and not isinstance(data, dict):
		raise ValueError("The data the flow starts with has to be an object.")
	if steps is not None and not isinstance(steps, dict):
		raise ValueError("The data of earlier steps has to be an object keyed by step.")
	out: dict = {"input": data or {}, "steps": steps or {}}
	if "item" in raw:
		out["item"] = raw["item"]
	return out
