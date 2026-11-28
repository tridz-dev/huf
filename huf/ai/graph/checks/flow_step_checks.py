"""Flow step checks run by the graph validator (split weights, App trigger error handling).

Split out of ``validator.py``, which imports these functions. ``ValidationError`` is imported inside each function
to avoid an import cycle with ``validator``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from huf.ai.graph.validation.result import ValidationError


def _check_split_weights(nodes: list) -> list[ValidationError]:
	"""Split steps: branch weights add up to 100 and the holdout share is 0-100 (H-W2-07), in draft and publish."""
	from huf.ai.graph.validation.result import ValidationError
	from huf.ai.flow.nodes.split import config_problems

	errors = []
	for node in nodes:
		if isinstance(node, dict) and node.get("type") == "split":
			for problem in config_problems(node.get("config") or {}):
				errors.append(ValidationError("SPLIT_WEIGHTS", node.get("id"), "config", problem))
	return errors


def _check_app_trigger_on_error(nodes: list) -> list[ValidationError]:
	"""An App trigger only refuses starts that are not its app's; an error step would let those carry on."""
	from huf.ai.graph.validation.result import ValidationError

	return [
		ValidationError("TRIGGER_ON_ERROR", node.get("id"), "on_error", "a trigger.app node must not declare on_error")
		for node in nodes
		if isinstance(node, dict) and node.get("type") == "trigger.app" and node.get("on_error") is not None
	]
