"""Shared HTTP helpers and constants for the Teams integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROVIDER_ID = "microsoft_teams"
TEAMS_SERVICE = "microsoft_teams"


def _requests_post(url: str, *, headers: Mapping[str, str], json_data: Any, timeout: int) -> Any:
	import requests

	# GW-05: this used to return the raw response without ever calling
	# raise_for_status(), so a non-2xx Bot Framework response (e.g. an
	# expired/invalid app_id+app_password pair) fell straight through to the
	# `.json()`/dict-shape handling below as if it had succeeded.
	response = requests.post(url, headers=headers, json=json_data, timeout=timeout)
	response.raise_for_status()
	return response
