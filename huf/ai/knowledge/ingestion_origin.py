# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Safe, short "where did this import come from" text for the Activity list.

source_config is stored as JSON and may hold secrets, so only whitelisted
keys ever leave the server.
"""

import json

SAFE_ORIGIN_KEYS = ("bucket", "prefix", "ssh_connection", "root_path", "path")
_SECRET_HINTS = ("secret", "password", "key", "token")


def sanitize_source_config(raw) -> dict | None:
	"""Return only whitelisted, non-secret string keys, or None."""
	if not raw:
		return None
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return None
	if not isinstance(raw, dict):
		return None
	out = {
		k: str(raw[k])[:200]
		for k in SAFE_ORIGIN_KEYS
		if k in raw and raw[k] and not any(h in k.lower() for h in _SECRET_HINTS)
	}
	return out or None
