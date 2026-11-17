# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Carousel template helpers (validate, build, read cards). Split from whatsapp_templates."""

from __future__ import annotations

from typing import Any

from huf.ai.gateway_adapters import whatsapp_templates as wt
from huf.ai.gateway_adapters.whatsapp_template_parts import send_params as sp


def _body_variable_at_edge(text: str) -> bool:
	return bool(wt._EDGE_VAR_START_RE.search(text) or wt._EDGE_VAR_END_RE.search(text))


def _validate_cards(
	payload: dict[str, Any], category: str, has_header: bool, footer: str, top_buttons: Any, body: str = ""
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
	"""Validate the ``cards`` of a media-carousel template (MARKETING only). Returns ``(cards, errors)``.

	Card input: ``{header_type IMAGE|VIDEO, sample | header_handle, body, sample_values, buttons}``.
	Create schema verified live 2026-11-18. Stable codes: ``carousel_card_count``, ``carousel_top_level_not_allowed``,
	``card_body_too_long`` (>160), ``card_too_many_buttons`` (>2), ``variable_at_edge`` (variable at start/end of a body).
	"""
	raw = payload.get("cards")
	errors: list[dict[str, str]] = []
	if raw in (None, "", []):
		return [], errors
	if category != "MARKETING":
		errors.append(wt._e("cards", "carousel_category_marketing_only", "Carousel templates must use the MARKETING category."))
	if not isinstance(raw, (list, tuple)):
		return [], errors + [wt._e("cards", "invalid", "cards must be a list.")]
	if not wt.CAROUSEL_MIN_CARDS <= len(raw) <= wt.CAROUSEL_MAX_CARDS:
		errors.append(wt._e("cards", "carousel_card_count", f"A carousel needs {wt.CAROUSEL_MIN_CARDS}-{wt.CAROUSEL_MAX_CARDS} cards."))
	if has_header or footer or top_buttons not in (None, "", []):
		errors.append(wt._e("cards", "carousel_top_level_not_allowed", "A carousel template has a body and cards only: no header, footer or top-level buttons."))
	if body and _body_variable_at_edge(body):
		errors.append(wt._e("body", "variable_at_edge", "Variables cannot be at the start or end of the carousel body (Meta 100/2388299)."))
	out: list[dict[str, Any]] = []
	for i, item in enumerate(raw):
		f = f"cards[{i}]"
		if not isinstance(item, dict):
			errors.append(wt._e(f, "invalid", "Each card must be an object."))
			continue
		htype = str(item.get("header_type") or "").strip().upper()
		sample = str(item.get("sample") or "").strip()
		handle = str(item.get("header_handle") or "").strip()
		if htype not in wt.CAROUSEL_HEADER_TYPES:
			errors.append(wt._e(f"{f}.header_type", "card_header_type", "Each card header must be IMAGE or VIDEO."))
		elif handle:
			pass
		elif not sample:
			errors.append(wt._e(f"{f}.sample", "required", f"A {htype} card header needs a sample file (URL or uploaded file path)."))
		elif not (wt.is_http_url(sample) or sample.startswith(("/files/", "/private/files/"))):
			errors.append(wt._e(f"{f}.sample", "invalid_sample", "Sample must be an http(s) URL or an uploaded file path such as /files/x.png."))
		body = str(item.get("body") if item.get("body") is not None else item.get("template") or "")
		pos: list[str] = []
		samples: list[str] = []
		if not body.strip():
			errors.append(wt._e(f"{f}.body", "card_body_missing", "Each card needs body text."))
		else:
			if len(body) > wt.CARD_BODY_MAX:
				errors.append(wt._e(f"{f}.body", "card_body_too_long", f"Card body is {len(body)} characters; the limit is {wt.CARD_BODY_MAX}."))
			if _body_variable_at_edge(body):
				errors.append(wt._e(f"{f}.body", "variable_at_edge", f"Variables cannot be at the start or end of card {i}'s body (Meta 100/2388299)."))
			pos, named = wt._check_variables(f"{f}.body", body, errors)
			if named:
				errors.append(wt._e(f"{f}.body", "card_named_unsupported", "Card bodies use numbered {{1}} variables."))
			samples = wt._split_samples(item.get("sample_values"))
			if pos and len(samples) != len(pos):
				errors.append(wt._e(f"{f}.sample_values", "sample_count", f"Provide exactly {len(pos)} sample value(s) for this card body."))
			elif not pos:
				samples = []
		btns, berrs = wt._validate_buttons(item.get("buttons"))
		errors.extend(wt._e(f"{f}.{e['field']}", e["code"], e["message"]) for e in berrs)
		if not btns:
			errors.append(wt._e(f"{f}.buttons", "card_buttons_required", "Each card needs at least one button."))
		if len(btns) > wt.CAROUSEL_MAX_CARD_BUTTONS:
			errors.append(wt._e(f"{f}.buttons", "card_too_many_buttons", f"A card allows at most {wt.CAROUSEL_MAX_CARD_BUTTONS} buttons."))
		if any(b["type"] not in wt.CAROUSEL_BUTTON_TYPES for b in btns):
			errors.append(wt._e(f"{f}.buttons", "card_button_type", "Card buttons must be quick-reply or URL."))
		out.append({
			"header_type": htype if htype in wt.CAROUSEL_HEADER_TYPES else "", "header_sample": sample,
			"header_handle": handle, "body": body, "sample_values": samples, "buttons": btns,
		})
	sigs = {tuple(b["type"] for b in c["buttons"]) for c in out}
	if len(sigs) > 1:
		errors.append(wt._e("cards", "card_buttons_mismatch", "Every card must have the same button types in the same order."))
	return out, errors


def _build_carousel_template(cards: list[dict[str, Any]]) -> dict[str, Any]:
	"""Meta ``CAROUSEL`` create component (card header handle, body, buttons). Schema from memory (unverified)."""
	out: list[dict[str, Any]] = []
	for card in cards:
		comps: list[dict[str, Any]] = [
			{"type": "HEADER", "format": card["header_type"], "example": {"header_handle": [card["header_handle"]]}}
		]
		body: dict[str, Any] = {"type": "BODY", "text": card["body"]}
		if card.get("sample_values"):
			body["example"] = {"body_text": [list(card["sample_values"])]}
		comps.append(body)
		btns: list[dict[str, Any]] = []
		for b in card["buttons"]:
			o: dict[str, Any] = {"type": b["type"], "text": b["text"]}
			if b["type"] == "URL":
				o["url"] = b["url"]
				if b.get("dynamic") and b.get("example"):
					o["example"] = [b["example"]]
			btns.append(o)
		comps.append({"type": "BUTTONS", "buttons": btns})
		out.append({"components": comps})
	return {"type": "CAROUSEL", "cards": out}


def carousel_cards(components: Any) -> list[dict[str, Any]] | None:
	"""Card definitions of a Meta ``CAROUSEL`` component (``None`` when the template has none).

	Each card: ``{header_type, body_vars, buttons: [{type, dynamic}]}`` (display and send validation).
	"""
	for comp in components if isinstance(components, list) else []:
		if not isinstance(comp, dict) or str(comp.get("type") or "").upper() != "CAROUSEL":
			continue
		cards: list[dict[str, Any]] = []
		for card in comp.get("cards") or []:
			info: dict[str, Any] = {"header_type": "", "body_vars": [], "buttons": []}
			for c in (card or {}).get("components") or []:
				if not isinstance(c, dict):
					continue
				ctype = str(c.get("type") or "").upper()
				if ctype == "HEADER":
					info["header_type"] = str(c.get("format") or "").upper()
					hh = (c.get("example") or {}).get("header_handle")
					if hh:
						info["header_example"] = str(hh[0])
				elif ctype == "BODY":
					info["body_vars"] = wt.variables(str(c.get("text") or ""))
					info["body"] = str(c.get("text") or "")
					bt = (c.get("example") or {}).get("body_text")
					info["sample_values"] = list(bt[0]) if bt and isinstance(bt[0], list) else []
				elif ctype == "BUTTONS":
					for b in c.get("buttons") or []:
						if isinstance(b, dict):
							btype = str(b.get("type") or "").upper()
							dynamic = btype == "URL" and "{{" in str(b.get("url") or "")
							entry = {"type": btype, "dynamic": dynamic, "text": b.get("text") or ""}
							if btype == "URL":
								entry["url"] = b.get("url") or ""
								ex = b.get("example")
								entry["example"] = str(ex[0]) if isinstance(ex, list) and ex else ""
							info["buttons"].append(entry)
			cards.append(info)
		return cards
	return None


def build_carousel_component(
	cards_def: list[dict[str, Any]], carousel_params: Any, errors: list[dict[str, str]]
) -> dict[str, Any] | None:
	"""Graph ``carousel`` component from per-card params, validated against the template's cards.

	``carousel_params`` is a list (or ``{"cards": [...]}``) of ``{"header": {"type"?, "id"|"link"} | "https://...",
	"body": [values], "buttons": [{"index", "sub_type": "url"|"quick_reply", "text"}]}`` in card order.
	Stable codes: ``carousel_required``, ``carousel_card_count``, ``card_header_required``,
	``card_header_invalid``, ``card_body_count_mismatch``, ``card_button_required``, ``card_button_unexpected``.
	"""
	if isinstance(carousel_params, dict):
		carousel_params = carousel_params.get("cards")
	if carousel_params is None or carousel_params == []:
		errors.append(wt._e("carousel_params", "carousel_required", f"This template is a carousel; provide {len(cards_def)} card(s) of values."))
		return None
	if not isinstance(carousel_params, list):
		errors.append(wt._e("carousel_params", "carousel_card_count", "carousel_params must be a list of cards."))
		return None
	given = len(carousel_params)
	if not wt.CAROUSEL_MIN_CARDS <= given <= wt.CAROUSEL_MAX_CARDS:
		errors.append(wt._e("carousel_params", "carousel_card_count", f"A carousel takes {wt.CAROUSEL_MIN_CARDS}-{wt.CAROUSEL_MAX_CARDS} cards; got {given}."))
		return None
	if given != len(cards_def):
		errors.append(wt._e("carousel_params", "carousel_card_count", f"This template has {len(cards_def)} card(s); got {given}."))
		return None
	out_cards: list[dict[str, Any]] = []
	for i, (card, definition) in enumerate(zip(carousel_params, cards_def)):
		field = f"carousel_params[{i}]"
		card = card if isinstance(card, dict) else {}
		comps: list[dict[str, Any]] = []
		# header media (id or https link)
		htype = definition.get("header_type") or ""
		raw = card.get("header")
		media: dict[str, Any] | None = None
		if isinstance(raw, str) and raw.strip():
			raw = {"link": raw.strip()}
		if not isinstance(raw, dict) or not (raw.get("id") or raw.get("link")):
			errors.append(wt._e(f"{field}.header", "card_header_required", f"Card {i} needs header media ({htype.lower() or 'image'} id or link)."))
		else:
			kind = str(raw.get("type") or htype or "image").lower()
			if htype and kind != htype.lower():
				errors.append(wt._e(f"{field}.header", "card_header_invalid", f"Card {i} header must be {htype.lower()}."))
			elif kind not in ("image", "video"):
				errors.append(wt._e(f"{field}.header", "card_header_invalid", "Card header media must be image or video."))
			elif raw.get("id"):
				media = {kind: {"id": str(raw["id"])}}
			elif wt.is_http_url(str(raw["link"]).strip()):
				media = {kind: {"link": str(raw["link"]).strip()}}
			else:
				errors.append(wt._e(f"{field}.header", "card_header_invalid", "Card header link must be an http(s) URL."))
			if media:
				comps.append({"type": "header", "parameters": [{"type": kind, **media}]})
		# body values
		values = card.get("body")
		values = list(values.values()) if isinstance(values, dict) else list(values or [])
		expected = len(definition.get("body_vars") or [])
		if len(values) != expected:
			errors.append(wt._e(f"{field}.body", "card_body_count_mismatch", f"Card {i} takes {expected} body parameter(s); got {len(values)}."))
		elif values:
			texts = [sp.validate_param_text(f"{field}.body[{j}]", v, errors) for j, v in enumerate(values)]
			comps.append({"type": "body", "parameters": [{"type": "text", "text": t} for t in texts]})
		# buttons
		btns, berr = sp.normalize_button_params(card.get("buttons"))
		errors += [{**e, "field": e["field"].replace("button_params", f"{field}.buttons", 1)} for e in berr]
		defs = definition.get("buttons") or []
		given_idx = set()
		for bp in btns:
			idx = bp["index"]
			bd = defs[idx] if idx < len(defs) else None
			ok = bd is not None and (
				(bp["sub_type"] == "quick_reply" and bd["type"] == "QUICK_REPLY")
				or (bp["sub_type"] == "url" and bd["type"] == "URL" and bd["dynamic"])
			)
			if not ok:
				errors.append(wt._e(f"{field}.buttons", "card_button_unexpected", f"Card {i} button {idx} does not take a {bp['sub_type']} parameter."))
			given_idx.add(idx)
		for idx, bd in enumerate(defs):
			if bd["type"] == "URL" and bd["dynamic"] and idx not in given_idx:
				errors.append(wt._e(f"{field}.buttons", "card_button_required", f"Card {i} button {idx} is a dynamic URL button and needs its URL suffix."))
		comps += wt.build_template_components(None, None, btns)
		out_cards.append({"card_index": i, "components": comps})
	return {"type": "carousel", "cards": out_cards}
