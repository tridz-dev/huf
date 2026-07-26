"""Shared helpers for the SerpApi ("SERP") integration tools.

The `serpapi` package is imported lazily inside `_client()` so this module (and
everything importing it) loads cleanly even when the package is not installed,
which keeps tests and registry scans working without the optional dependency.
"""

from huf.ai.tools.credentials import require_credential

SERVICE_NAME = "serpapi"


class SerpValidationError(ValueError):
	"""Invalid tool input. Surfaced as an error envelope without touching last_error."""


def _client(api_key: str | None = None):
	"""Build a SerpApi client, resolving the API key lazily per call."""
	import serpapi

	return serpapi.Client(api_key=api_key or require_credential(SERVICE_NAME, "api_key"))


def _search(params: dict, api_key: str | None = None) -> dict:
	"""Run a SerpApi search and return the raw result dict."""
	return _client(api_key=api_key).search(params)


def _safe_float(value) -> float:
	if value is None:
		return 0.0
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def _as_int(value, field: str):
	"""Coerce an optional int input; None/'' -> None, bad value -> SerpValidationError."""
	if value in (None, ""):
		return None
	try:
		return int(value)
	except (TypeError, ValueError):
		raise SerpValidationError(f"{field} must be a valid integer.")


def _as_bool(value) -> bool:
	if isinstance(value, bool):
		return value
	return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_csv(value) -> str | None:
	"""Accept a list or a comma string; return a clean comma-separated string."""
	if value in (None, ""):
		return None
	if isinstance(value, list | tuple):
		parts = [str(v).strip() for v in value if str(v).strip()]
	else:
		parts = [p.strip() for p in str(value).split(",") if p.strip()]
	return ",".join(parts) or None
