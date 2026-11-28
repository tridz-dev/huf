# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Route a send step's trailing tokens to the template's buttons.

The guard (``guard_steps._params_match``) wants one token per body variable, text header variable and
*required button* (a dynamic URL button, a COPY_CODE button), in that order. A button token is not a body
parameter: Meta takes it as a ``button`` component. :func:`split` cuts the token names accordingly so the
transport never pushes a button value into the body list.
"""

from __future__ import annotations

import frappe

URL = "url"
COPY_CODE = "copy_code"


def required_buttons(gateway: str | None, template: str | None) -> list[dict]:
	"""The template's buttons that need a token, in slot order (``[]`` for a text send or unknown template)."""
	if not template:
		return []
	from huf.ai.channels.outbound import guard_steps

	loaded = guard_steps._load_template(gateway, template)
	if not loaded:
		return []
	return [b for b in loaded[1]["buttons"] if b.get("required")]


def split(token_names: list[str], buttons: list[dict], values: dict) -> tuple[list[str], list[dict]]:
	"""``(body token names, button_params)``: the last ``len(buttons)`` tokens belong to the buttons."""
	if not buttons:
		return list(token_names), []
	if len(token_names) < len(buttons):
		raise frappe.ValidationError("button_token_missing")
	body, button_names = token_names[: len(token_names) - len(buttons)], token_names[len(token_names) - len(buttons) :]
	params = []
	for button, name in zip(buttons, button_names, strict=True):
		value = str(values[name])
		if button["sub_type"] == COPY_CODE:
			params.append({"index": button["index"], "sub_type": COPY_CODE, "code": value})
		else:
			params.append({"index": button["index"], "sub_type": URL, "text": value})
	return body, params
