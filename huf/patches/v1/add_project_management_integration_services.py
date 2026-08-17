def execute():
	"""Register Linear, ClickUp, Trello, Notion, Zendesk, Cal.com, and Zoom services.

	The integration tool handlers and Agent Tool Function sync shipped in
	feat/integration-tools-completion, but `register_integration_services()` was
	not updated at the same time. Existing sites therefore have the tools in the
	database while the Integration Catalog UI has nothing to connect against.
	"""
	from huf.install import register_integration_services

	register_integration_services()
