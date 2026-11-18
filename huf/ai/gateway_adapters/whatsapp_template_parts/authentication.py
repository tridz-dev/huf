# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""AUTHENTICATION (OTP) template helpers. Split from whatsapp_templates."""

from __future__ import annotations

import re
from typing import Any

from huf.ai.gateway_adapters import whatsapp_templates as wt


def _validate_authentication(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
	"""Spec for an AUTHENTICATION template (fixed Meta format, copy-code button)."""
	errors: list[dict[str, str]] = []
	for key, label in (("header", "header"), ("header_type", "header"), ("footer", "footer"), ("buttons", "buttons")):
		if payload.get(key) not in (None, "", [], {}):
			errors.append(wt._e(key, "not_allowed", f"Authentication templates have a fixed format and no custom {label}."))
	if wt._ttl_value(payload) is not None:
		errors.append(wt._e("ttl_seconds", "ttl_not_allowed", "ttl_seconds can only be set on UTILITY templates."))
	recommendation = payload.get("add_security_recommendation")
	if recommendation is None:
		recommendation = False
	if not isinstance(recommendation, bool):
		errors.append(wt._e("add_security_recommendation", "invalid", "add_security_recommendation must be true or false."))
		recommendation = False
	expiry = payload.get("code_expiration_minutes")
	if expiry == "":
		expiry = None
	if expiry is not None:
		if isinstance(expiry, bool) or not isinstance(expiry, int):
			errors.append(wt._e("code_expiration_minutes", "invalid_expiry", "code_expiration_minutes must be an integer."))
			expiry = None
		elif not wt.OTP_EXPIRY_MIN <= expiry <= wt.OTP_EXPIRY_MAX:
			errors.append(
				wt._e("code_expiration_minutes", "expiry_out_of_range", f"code_expiration_minutes must be {wt.OTP_EXPIRY_MIN}-{wt.OTP_EXPIRY_MAX}.")
			)
	button_text = str(payload.get("otp_button_text") or wt.OTP_BUTTON_TEXT_DEFAULT).strip()
	if len(button_text) > wt.BUTTON_TEXT_MAX:
		errors.append(wt._e("otp_button_text", "too_long", f"Button text is {len(button_text)} characters; the limit is {wt.BUTTON_TEXT_MAX}."))
	declared = str(payload.get("parameter_format") or "").strip().upper()
	if declared and declared != "POSITIONAL":
		errors.append(wt._e("parameter_format", "parameter_format_mismatch", "Authentication templates use a positional code variable."))
	spec = {
		"body": wt.OTP_BODY + (wt.OTP_BODY_SECURITY if recommendation else ""),
		"parameter_format": "POSITIONAL",
		"sample_values": [],
		"named_samples": [],
		"header_type": "",
		"header_text": "",
		"header_sample": "",
		"header_variable": "",
		"header_handle": "",
		"footer": f"This code expires in {expiry} minutes." if isinstance(expiry, int) else "",
		"buttons": [],
		"category": "AUTHENTICATION",
		"ttl_seconds": None,
		"notes": [],
		"add_security_recommendation": recommendation,
		"code_expiration_minutes": expiry if isinstance(expiry, int) else None,
		"otp_button_text": button_text,
	}
	return spec, errors


def build_otp_components(code: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
	"""Send components for an authentication template: the code as the body parameter and as
	the copy-code (url) button parameter. The code is never echoed into error messages."""
	if isinstance(code, dict):
		code = next(iter(code.values()), None)
	elif isinstance(code, (list, tuple)):
		if len(code) != 1:
			return [], [wt._e("body_params", "param_count_mismatch", "An authentication template takes exactly one parameter: the code.")]
		code = code[0]
	text = str(code if code is not None else "").strip()
	if not text:
		return [], [wt._e("body_params", "empty_param", "The one-time code cannot be empty.")]
	if len(text) > wt.OTP_CODE_MAX or not re.fullmatch(r"[A-Za-z0-9]+", text):
		return [], [wt._e("body_params", "invalid_code", f"The code must be 1-{wt.OTP_CODE_MAX} letters or digits.")]
	return [
		{"type": "body", "parameters": [{"type": "text", "text": text}]},
		{"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": text}]},
	], []
