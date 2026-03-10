import json
import frappe


def handle_search(**kwargs):
	"""Search the web using DuckDuckGo."""
	try:
		from duckduckgo_search import DDGS
	except ImportError:
		return json.dumps({"success": False, "error": "duckduckgo-search is required. Install with: pip install duckduckgo-search"})

	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		max_results = int(kwargs.get("max_results", 5))
		with DDGS() as ddgs:
			results = list(ddgs.text(query, max_results=max_results))
		return json.dumps({"success": True, "count": len(results), "results": results})
	except Exception as e:
		frappe.log_error(f"DuckDuckGo Search Error: {str(e)}", "DuckDuckGo Search Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_news(**kwargs):
	"""Search news using DuckDuckGo."""
	try:
		from duckduckgo_search import DDGS
	except ImportError:
		return json.dumps({"success": False, "error": "duckduckgo-search is required. Install with: pip install duckduckgo-search"})

	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		max_results = int(kwargs.get("max_results", 5))
		with DDGS() as ddgs:
			results = list(ddgs.news(query, max_results=max_results))
		return json.dumps({"success": True, "count": len(results), "results": results})
	except Exception as e:
		frappe.log_error(f"DuckDuckGo News Error: {str(e)}", "DuckDuckGo Search Tool")
		return json.dumps({"success": False, "error": str(e)})
