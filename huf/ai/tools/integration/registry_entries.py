"""Registry helpers shared by ``huf.ai.tools._registry``: service stamping."""


def with_service(tools: list[dict], service: str) -> list[dict]:
	"""Stamp the owning Integration Service key onto each tool definition.

	Tools are already grouped one list per service in this file, so the
	association is declared once here instead of repeated on every entry. The
	key must match an `Integration Service` docname, because that link is what
	lets the UI tell a user which account a tool needs before they attach it.
	An entry that already names a service keeps its own value.

	`service` is catalog metadata only (UI hint, `integration_utils` lookups): it
	does NOT gate which agents can use the tool. App Provided rows are fully
	owned by the migrate sync (`sync_discovered_tools`), which upserts every
	field. Per-conversation gating (e.g. `telegram_admin` only inside a Telegram
	gateway chat with admin-enabled groups) is enforced by the tool handler.
	"""
	return [{**tool, "service": tool.get("service") or service} for tool in tools]
