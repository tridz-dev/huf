import frappe


def execute():
	"""
	Audit App Provided tool functions against the hook-declared allow-set
	(huf.ai.tool_registry.get_hook_declared_function_paths). Report only;
	does not delete or modify data. Run manually before deploying ST-05.1/
	ST-05.2 so any row that would start failing validation is known ahead
	of time.
	"""
	from huf.ai.tool_registry import get_hook_declared_function_paths

	allowed_paths = get_hook_declared_function_paths(use_cache=False)

	offending = []
	for tool_doc in frappe.get_all(
		"Agent Tool Function",
		filters={"types": "App Provided"},
		fields=["name", "function_path", "tool_name"],
	):
		if tool_doc.function_path not in allowed_paths:
			offending.append(
				{"tool": tool_doc.name, "tool_name": tool_doc.tool_name, "path": tool_doc.function_path}
			)

	if offending:
		frappe.log_error(
			title="Security Audit: App Provided tool paths outside hook allow-set",
			message=(
				f"audit_app_provided_tool_paths: found {len(offending)} App Provided tool(s) "
				f"whose function_path is not declared by any installed app's huf_tools hook:\n"
				+ "\n".join(f"  {row}" for row in offending)
			),
		)
