import json


def handle_search(**kwargs):
	"""Search the web using DuckDuckGo."""
	try:
		from duckduckgo_search import DDGS
	except ImportError:
		return json.dumps({"error": "duckduckgo-search is required. Install with: pip install duckduckgo-search"})

	try:
		max_results = int(kwargs.get("max_results", 5))
		with DDGS() as ddgs:
			results = list(ddgs.text(kwargs["query"], max_results=max_results))
		return json.dumps({"count": len(results), "results": results})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_news(**kwargs):
	"""Search news using DuckDuckGo."""
	try:
		from duckduckgo_search import DDGS
	except ImportError:
		return json.dumps({"error": "duckduckgo-search is required. Install with: pip install duckduckgo-search"})

	try:
		max_results = int(kwargs.get("max_results", 5))
		with DDGS() as ddgs:
			results = list(ddgs.news(kwargs["query"], max_results=max_results))
		return json.dumps({"count": len(results), "results": results})
	except Exception as e:
		return json.dumps({"error": str(e)})
