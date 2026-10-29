"""Registry helpers shared by ``huf.ai.tools._registry``: service stamping and the ``http_request`` tool."""


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


def http_tools(_p) -> list[dict]:
	"""Tool definitions for the registry; ``_p`` is the registry's parameter-row builder."""
	return [
		{
			"tool_name": "http_request",
			"description": "Make an outbound HTTP request to a public URL. Private/internal addresses are blocked, redirects are re-validated, Guest users are blocked. Returns JSON {success, status_code, headers, body}; success is false for non-2xx.",
			"function_path": "huf.ai.http_handler.http_request",
			"category": "Developer Tools",
			"parameters": [
				_p("url", required=True, description="Absolute http(s) URL"),
				_p("method", description="GET, POST, PUT, PATCH, DELETE or HEAD (default GET)"),
				_p("headers", type="object", description="Request headers as a JSON object"),
				_p("body", description="Request body: JSON object/array or raw string"),
			],
		},
	]
