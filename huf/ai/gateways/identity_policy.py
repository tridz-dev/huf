"""Providers whose people must link their own account before anything runs.

For these providers an unlinked sender only ever receives a private connect
prompt, so an ``Open`` direct-message policy is safe: the identity link is the
authorization. Kept dependency-free so doctypes and services can both import it.
"""

IDENTITY_REQUIRED_PROVIDERS = frozenset({"slack", "microsoft teams"})


def is_identity_required(provider) -> bool:
	return str(provider or "").strip().lower() in IDENTITY_REQUIRED_PROVIDERS
