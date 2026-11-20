# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Argument-shaping helpers split out of ``huf.ai.tools.whatsapp``."""

from __future__ import annotations

import json
from typing import Any, Optional


def _json_list(value: Any) -> list | None:
	"""A list argument that may arrive as a JSON string; None when it is not a list."""
	if value in (None, ""):
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			return None
	if isinstance(value, dict):
		return [value]
	return value if isinstance(value, list) else None


def _body_values(parameters: Any) -> Any:
	"""Body parameters as the bridge takes them: strings in a list, or a ``{name: value}`` map."""
	if isinstance(parameters, dict):
		return {str(k): str(v) for k, v in parameters.items()}
	return [p if isinstance(p, dict) else str(p) for p in parameters]
