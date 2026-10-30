"""What a run came to for the business: the End step's ``outcome`` ``{label, tone}``, recorded on the Flow Run.

``Flow Run.outcome_label`` and ``Flow Run.outcome_tone`` hold it once the run reaches an End step that declares one.
The label may use ``{input.field}`` placeholders (filled in when the run ends); a missing label is "Finished" and a
missing or odd tone reads as neutral. A run whose End step declares nothing records nothing: the run page then
falls back to what an approver decided (``compute_outcome`` in ``shape.py``), else to the plain status.
"""

from __future__ import annotations

DEFAULT_LABEL = "Finished"
DEFAULT_TONE = "neutral"
TONES = ("good", "neutral", "bad")
MAX_LABEL = 60


def resolve_outcome(raw, ctx=None) -> dict | None:
	"""``{"label", "tone"}`` for an End step's ``outcome`` setting, or None when it declares none."""
	if not isinstance(raw, dict):
		return None
	label = str(raw.get("label") or "").strip()
	if label and ctx is not None:
		from huf.ai.flow.support.router_text import render_text_refs

		label = render_text_refs(label, ctx)
	label = " ".join(label.split())[:MAX_LABEL] or DEFAULT_LABEL
	tone = str(raw.get("tone") or "").lower()
	return {"label": label, "tone": tone if tone in TONES else DEFAULT_TONE}


def record_outcome(flow_run, raw, ctx=None) -> dict | None:
	"""Write the End step's outcome onto the run (``db_set``: the run document is saved elsewhere by status transitions)."""
	outcome = resolve_outcome(raw, ctx)
	if outcome:
		flow_run.db_set({"outcome_label": outcome["label"], "outcome_tone": outcome["tone"]}, update_modified=False)
	return outcome


def stored_outcome(row) -> dict | None:
	"""The recorded outcome of a Flow Run (document, row or dict), or None."""
	get = row.get if hasattr(row, "get") else (lambda key: getattr(row, key, None))
	label = str(get("outcome_label") or "").strip()
	if not label:
		return None
	tone = str(get("outcome_tone") or "").lower()
	return {"label": label, "tone": tone if tone in TONES else DEFAULT_TONE}
