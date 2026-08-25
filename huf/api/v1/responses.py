"""Success-envelope helpers for the Huf public developer API (v1)."""

from typing import Optional


def success_response(data, request_id: str, meta: Optional[dict] = None) -> dict:
	"""Build the stable JSON success envelope.

	Shape: `{"data": ..., "request_id": ..., "meta": ...}`
	"""
	return {
		"data": data,
		"request_id": request_id,
		"meta": meta or {},
	}
