"""``stop`` node: end the flow at this step.

Config: ``message`` (template text, shown as the reason) and ``as`` (``error`` | ``success``, default ``error``).
``error`` fails the run with the message, so the steps after it never run. ``success`` ends the run as finished.
A stop node has no successor of its own.
"""

from __future__ import annotations

from huf.ai.graph.templates import TemplateError, render_template


def exec_stop(flow_run, node: dict, config: dict, settings: dict, context) -> dict:
	try:
		message = render_template(str(config.get("message") or ""), context.reference_roots()).strip()
	except TemplateError as exc:
		return {"status": "failed", "error": str(exc)}
	if config.get("as") == "success":
		return {"status": "success", "output": {"message": message}}
	if not message:
		return {"status": "failed", "error": "Write the message to show when the flow stops."}
	return {"status": "failed", "error": message}
