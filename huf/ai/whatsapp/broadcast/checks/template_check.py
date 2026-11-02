# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""What a send of a template needs, and what one recipient's values would be refused for (split out of ``limits``)."""

from __future__ import annotations

from typing import Any


def _loads(value: Any) -> Any:
	"""Same decoding as broadcast_send._json (JSON string -> value, blank -> None)."""
	from huf.ai.whatsapp.broadcast.send import _json

	return _json(value)


def _samples(account: str | None, template: str, view: dict[str, Any]) -> dict[str, str]:
	"""``{variable: sample}`` for the body, from the Template Extra (named_samples / components_json)."""
	from huf.ai.gateway_adapters import whatsapp_template_guard as guard

	try:
		extra = guard.get_extra(account, template) or {}
	except Exception:  # noqa: BLE001
		extra = {}
	out: dict[str, str] = {}
	for item in extra.get("named_samples") or []:
		if isinstance(item, dict) and item.get("name"):
			out[str(item["name"])] = str(item.get("example") or "")
	if not out:
		for comp in extra.get("components_json") or []:
			if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
				rows = (comp.get("example") or {}).get("body_text") or []
				for i, val in enumerate(rows[0] if rows else []):
					out[str(i + 1)] = str(val)
	return out


def template_requirements(template: str) -> dict[str, Any] | None:
	"""What a send of WhatsApp Templates row ``template`` needs, derived with the bridge's own helpers.

	``{"tpl", "view", "parameter_format", "body": [{name|index, sample}], "header": {...}|None,
	"buttons": [...]}`` or None when the row does not exist.
	"""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.gateway_adapters import whatsapp_templates as wt

	tpl = bridge._template_row(template or "")
	if not tpl:
		return None
	view = bridge._send_view(tpl)
	tv = wt._template_view(view)
	named = tv["fmt"] == "NAMED"
	samples = _samples(tpl.get("whatsapp_account"), template, view)
	body = [
		({"name": v, "sample": samples.get(v)} if named else {"index": int(v), "sample": samples.get(v)})
		for v in tv["body_vars"]
	]
	htype = tv["header_type"]
	header: dict[str, Any] | None = None
	if htype in ("", "TEXT") and tv["header_vars"]:
		v = tv["header_vars"][0]
		header = {"type": "TEXT", "required": True, ("name" if named else "index"): v if named else int(v), "sample": None}
	elif htype in wt.MEDIA_HEADER_TYPES:
		has_default = htype == "IMAGE" and wt.is_http_url(str(tpl.get("sample") or ""))
		header = {"type": htype, "required": not has_default}
	elif htype == "LOCATION":
		header = {"type": htype, "required": True}
	buttons = []
	for i, b in enumerate(tpl.get("buttons") or []):
		kind = b.get("button_type")
		if kind == "Visit Website" and b.get("url_type") == "Dynamic":
			buttons.append({"index": i, "sub_type": "url", "required": True, "label": b.get("button_label")})
		elif kind == wt.DOCTYPE_BUTTON_TYPE["COPY_CODE"]:
			buttons.append({"index": i, "sub_type": "copy_code", "required": True, "label": b.get("button_label")})
		elif kind == "Quick Reply":
			buttons.append({"index": i, "sub_type": "quick_reply", "required": False, "label": b.get("button_label")})
	return {
		"tpl": tpl, "view": view, "parameter_format": tv["fmt"], "tv": tv,
		"body": body, "header": header, "buttons": buttons,
	}


def send_problems(req: dict[str, Any], body: Any, header: Any, button: Any) -> dict[str, list[str]]:
	"""What the send of one recipient would be refused for, using the same validation as ``bridge.send_template``.

	``{"missing": [labels], "extra": [labels], "invalid": [messages]}`` (all empty when the send would pass).
	"""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.gateway_adapters import whatsapp_templates as wt

	tpl, view, tv = req["tpl"], req["view"], req["tv"]
	button_list = button if isinstance(button, list) else ([button] if button else [])
	other, copy_comps, errors = bridge.split_copy_code_params(button_list)
	header_raw = bridge._header_list(header, True)
	components, build_errors = wt.build_send_components(view, body, header_raw, other)
	errors += build_errors
	seen = {(e["field"], e["code"]) for e in errors}
	errors += [
		e for e in bridge._check_send_against_template(tpl, view, body, header_raw, other, copy_comps)
		if (e["field"], e["code"]) not in seen
	]
	if tv["header_type"] in wt.MEDIA_HEADER_TYPES and not any(c.get("type") == "header" for c in components):
		if not (tv["header_type"] == "IMAGE" and wt.is_http_url(str(tpl.get("sample") or ""))):
			errors.append(wt._e("header_params", "required", f"This template has an {tv['header_type']} header; provide a media link."))

	named = tv["fmt"] == "NAMED"
	names = list(tv["body_vars"])
	given = list(body.values()) if isinstance(body, dict) else list(body or [])
	missing: list[str] = []
	extra: list[str] = []
	invalid: list[str] = []
	for e in errors:
		field, code, msg = e["field"], e["code"], e.get("message", "")
		if code == "param_missing":
			missing.append(field.split(".", 1)[-1])
		elif code == "param_count_mismatch" and field == "body_params":
			if len(given) < len(names):
				missing += names[len(given):] if not isinstance(body, dict) or not named else names
			else:
				extra.append(f"{len(given) - len(names)} extra body value(s)")
		elif code == "param_unknown":
			extra.append(field.split(".", 1)[-1])
		elif code in ("not_expected", "unexpected"):
			extra.append(field)
		elif code == "required":
			missing.append("header" if field.startswith("header") else field.replace("_params", ""))
		else:
			invalid.append(msg or f"{field}: {code}")
	dedupe = lambda xs: list(dict.fromkeys(xs))  # noqa: E731
	return {"missing": dedupe(missing), "extra": dedupe(extra), "invalid": dedupe(invalid)}


