# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Argument parsing for send_template ``carousel_params``, split out of ``huf.ai.tools.whatsapp``."""

from __future__ import annotations

import json
from typing import Any

from huf.ai.whatsapp.parts.tool_args import _json_list


def _carousel_list(value: Any) -> list | None:
	"""Per-card ``carousel_params``: a list, a JSON list, or ``{"cards": [...]}``; None when it is none of these."""
	if isinstance(value, str) and value.strip():
		try:
			value = json.loads(value)
		except ValueError:
			return None
	if isinstance(value, dict):
		if "cards" not in value:
			return None
		value = value["cards"]
	return _json_list(value)
