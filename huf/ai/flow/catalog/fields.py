"""The data a step can use, shown the way people think of it ("Customer name: Ada Lovelace").

Frappe-free and pure so it is tested without a site. ``catalog_api.get_data_catalog`` feeds it the saved flow, the
latest run and (for a data trigger) the document type, and returns what the "Use data" picker shows.

A *field* is ``{path, label, type, sample, list?, advanced_only?}``:

* ``path`` is a reference path the engine can read (``input.customer.name``, ``n_http.items[0]``). It always matches the
  reference grammar in docs/flow/FIELD_CONTRACT.md: ``(input|trigger|row|foreach.item|foreach.index|<node_id>)`` followed by
  ``.name`` or ``[n]``. A key that cannot be written that way (``order-total``, ``a b``) is listed with ``advanced_only``
  and no path, so the picker can say so instead of inserting something that would not resolve.
* ``label`` is the plain name (``Customer > Name`` for something inside another thing).
* ``type`` is ``text``, ``number``, ``yes_no``, ``date``, ``object`` or ``list``.
* ``sample`` is the real value for a scalar and a short sentence for an object or a list (never JSON).
* ``list`` (lists only) is ``{count, item_type, item_texts, item_fields}``; item fields carry paths *relative to one item*.

Samples are trimmed and have secrets hidden before they get here (``trigger_sample.redact_sample``); this module caps
the depth, the number of fields and the size of what it returns again, so one odd payload cannot flood the picker.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping

from huf.ai.flow.support.humanize import format_scalar, label_for, summarize
from huf.ai.flow.support.trigger_sample import MASK

MAX_DEPTH = 3
MAX_FIELDS = 40
MAX_TEXT = 80
MAX_BYTES = 64 * 1024
MAX_ITEM_FIELDS = 12

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: What a reference may start with (FIELD_CONTRACT section 2). A step id is any identifier.
SPECIAL_ROOTS = ("input", "trigger", "row", "foreach.item", "foreach.index")
_PATH_RE = re.compile(r"^(input|trigger|row|foreach\.(?:item|index)|[A-Za-z_][A-Za-z0-9_]*)(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:Z|[+-]\d{2}:?\d{2})?)?$")


def is_valid_path(path: Any) -> bool:
	"""True when ``path`` is a reference the engine and the save-time validator accept."""
	return isinstance(path, str) and bool(_PATH_RE.match(path))


def value_type(value: Any) -> str:
	if isinstance(value, bool):
		return "yes_no"
	if isinstance(value, (int, float)):
		return "number"
	if isinstance(value, Mapping):
		return "object"
	if isinstance(value, (list, tuple)):
		return "list"
	if isinstance(value, str) and _ISO_DATE.match(value):
		return "date"
	return "text"


def _clip(text: str, limit: int = MAX_TEXT) -> str:
	text = " ".join(text.split())
	return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def sample_for(value: Any, labels: Mapping[str, str] | None = None) -> Any:
	"""What the picker prints next to a field: the scalar itself, or one short sentence for an object or a list."""
	if value is None or value == "":
		return None
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)):
		return value
	if isinstance(value, str):
		if value == MASK:
			return "(hidden)"
		return _clip(format_scalar(value) if value else value)
	text = summarize(value, labels)
	return _clip(text) if text else None


def _list_info(items: list, path: str, labels: Mapping[str, str] | None) -> dict:
	first = next((i for i in items if i is not None), None)
	info: dict = {"count": len(items), "item_type": value_type(first) if first is not None else "text", "item_fields": []}
	texts = [sample_for(i, labels) for i in items[:5] if i is not None]
	info["item_texts"] = [str(t) for t in texts if t is not None]
	if isinstance(first, Mapping):
		info["item_fields"] = _fields(first, "", 0, labels, [], MAX_ITEM_FIELDS, with_lists=False)
	return info


def _fields(
	obj: Mapping,
	prefix: str,
	depth: int,
	labels: Mapping[str, str] | None,
	trail: list[str],
	budget: int,
	with_lists: bool = True,
) -> list[dict]:
	"""Fields of one object, depth first, objects before what is inside them."""
	out: list[dict] = []
	for key, value in obj.items():
		if len(out) >= budget:
			break
		skey = str(key)
		if skey.startswith("_"):
			continue
		label_parts = [*trail, label_for(skey, labels)]
		label = " > ".join(label_parts)
		kind = value_type(value)
		path = (f"{prefix}.{skey}" if prefix else skey) if IDENT.match(skey) else None
		field: dict = {"path": path, "label": label, "type": kind, "sample": sample_for(value, labels)}
		if path is None:
			field["advanced_only"] = True
			out.append(field)
			continue
		if kind == "list" and with_lists:
			field["list"] = _list_info(list(value), path, labels)
		out.append(field)
		if kind == "object" and depth + 1 < MAX_DEPTH:
			room = budget - len(out)
			if room > 0:
				out.extend(_fields(value, path, depth + 1, labels, label_parts, room, with_lists))
	return out[:budget]


def infer_fields(sample: Any, root: str, labels: Mapping[str, str] | None = None, root_label: str = "Result", budget: int = MAX_FIELDS) -> list[dict]:
	"""Fields found in one sample, each path starting with ``root`` (``input`` for a trigger, a step id for a step)."""
	if isinstance(sample, Mapping):
		return _fields(sample, root, 0, labels, [], budget)
	if sample is None or sample == "":
		return []
	kind = value_type(sample)
	field: dict = {"path": root, "label": root_label, "type": kind, "sample": sample_for(sample, labels)}
	if kind == "list":
		field["list"] = _list_info(list(sample), root, labels)
	return [field]


def trim_to_budget(steps: list[dict], max_bytes: int = MAX_BYTES) -> list[dict]:
	"""Drop fields from the end of the biggest step until the whole answer fits ``max_bytes``."""
	def size() -> int:
		return len(json.dumps(steps, default=str).encode())

	while size() > max_bytes:
		biggest = max((s for s in steps if s.get("fields")), key=lambda s: len(s["fields"]), default=None)
		if biggest is None:
			break
		biggest["fields"].pop()
	return steps


# ---------------------------------------------------------------------------- the flow graph
def graph_nodes(graph: Any) -> list[dict]:
	nodes = graph.get("nodes") if isinstance(graph, dict) else None
	if isinstance(nodes, dict):
		nodes = [{"id": k, **(v or {})} for k, v in nodes.items()]
	return [n for n in (nodes or []) if isinstance(n, dict) and n.get("id")]


def _targets(node: dict) -> list[str]:
	config = node.get("config") or {}
	ntype = node.get("type")
	out = [node.get("next"), node.get("on_error")]
	if ntype == "condition":
		out += [config.get("on_true"), config.get("on_false")]
	elif ntype in ("router.llm", "router.decision"):
		out += [o.get("node_id") for o in config.get("options") or [] if isinstance(o, dict)]
		out.append(config.get("default"))
	elif ntype == "human.approval":
		out += [config.get("approve_next"), config.get("reject_next"), config.get("timeout_next")]
	elif ntype == "foreach":
		out += list(config.get("body") or [])
	return [t for t in out if isinstance(t, str) and t]


def _entry_roots(graph: dict, nodes: list[dict]) -> list[str]:
	entry = graph.get("entry")
	roots = list(entry) if isinstance(entry, list) else ([entry] if entry else [])
	if roots:
		return roots
	return [n["id"] for n in nodes if str(n.get("type", "")).startswith("trigger.")]


def _adjacency(nodes: list[dict]) -> dict[str, list[str]]:
	ids = {n["id"] for n in nodes}
	return {n["id"]: [t for t in _targets(n) if t in ids] for n in nodes}


def guaranteed_predecessors(graph: dict, node_id: str) -> set[str]:
	"""Steps that sit on EVERY path from a trigger to ``node_id`` (never ``node_id`` itself).

	Same rule as the editor's picker (``lib/flow/flowRefs.ts``) and the save-time check: a step may read only what
	always ran before it.
	"""
	nodes = graph_nodes(graph)
	adjacency = _adjacency(nodes)
	incoming: dict[str, list[str]] = {}
	for source, targets in adjacency.items():
		for target in targets:
			incoming.setdefault(target, []).append(source)
	ancestors: set[str] = set()
	stack = [node_id]
	while stack:
		cur = stack.pop()
		for parent in incoming.get(cur, []):
			if parent != node_id and parent not in ancestors:
				ancestors.add(parent)
				stack.append(parent)
	roots = _entry_roots(graph, nodes)

	def reachable_without(skip: str) -> bool:
		seen = {r for r in roots if r != skip}
		queue = list(seen)
		while queue:
			cur = queue.pop()
			if cur == node_id:
				return True
			for nxt in adjacency.get(cur, []):
				if nxt != skip and nxt not in seen:
					seen.add(nxt)
					queue.append(nxt)
		return False

	return {a for a in ancestors if not reachable_without(a)}


def depth_from_entry(graph: dict) -> dict[str, int]:
	"""Longest distance from a trigger, so "newest first" means closest to the step being edited first."""
	nodes = graph_nodes(graph)
	adjacency = _adjacency(nodes)
	depth: dict[str, int] = {}
	visiting: set[str] = set()

	def walk(nid: str, d: int) -> None:
		if nid in visiting or depth.get(nid, -1) >= d:
			return
		visiting.add(nid)
		depth[nid] = d
		for nxt in adjacency.get(nid, []):
			walk(nxt, d + 1)
		visiting.discard(nid)

	for root in _entry_roots(graph, nodes):
		walk(root, 0)
	return depth


def enclosing_loop(graph: dict, node_id: str) -> dict | None:
	"""The loop step whose body contains ``node_id`` (the nearest one), or None."""
	nodes = graph_nodes(graph)
	by_id = {n["id"]: n for n in nodes}
	adjacency = _adjacency(nodes)
	for loop in (n for n in nodes if n.get("type") == "foreach"):
		stack = [b for b in (loop.get("config") or {}).get("body") or [] if b in by_id]
		seen: set[str] = set()
		while stack:
			cur = stack.pop()
			if cur == node_id:
				return loop
			if cur in seen:
				continue
			seen.add(cur)
			for nxt in adjacency.get(cur, []):
				if nxt != loop["id"]:
					stack.append(nxt)
	return None


def loop_item_fields(items_path: str | None, steps: Iterable[Mapping]) -> list[dict]:
	"""Fields of the current item of a loop, found from the list the loop goes through (``foreach.item.name``)."""
	if not items_path:
		return []
	for step in steps:
		for field in step.get("fields") or []:
			if field.get("path") == items_path and field.get("list"):
				return [
					{**f, "path": f"foreach.item.{f['path']}" if f.get("path") else None}
					for f in field["list"].get("item_fields") or []
				]
	return []
