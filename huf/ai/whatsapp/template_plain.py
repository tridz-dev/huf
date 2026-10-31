"""Plain-language wording for template states shown to users."""

_STATUS_PLAIN = {
	"PENDING": "in review by WhatsApp",
	"IN_APPEAL": "in appeal",
	"DISABLED": "disabled",
	"LIMIT_EXCEEDED": "over the template limit",
}


def not_editable_text(status):
	"""Plain-language reason a template cannot be edited (no raw Meta status words)."""
	key = str(status or "").upper().replace(" ", "_")
	state = _STATUS_PLAIN.get(key) or (key.replace("_", " ").lower() if key else "")
	lead = f"This template is {state}, so it can't be edited right now." if state else "This template can't be edited right now."
	return f"{lead} You can edit approved, rejected or paused templates."
