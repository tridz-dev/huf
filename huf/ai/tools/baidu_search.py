import json

import requests


def handle_search(**kwargs):
	"""Search using Baidu (Chinese search engine)."""
	try:
		query = kwargs["query"]
		max_results = int(kwargs.get("max_results", 5))

		resp = requests.get(
			"https://www.baidu.com/s",
			params={"wd": query, "rn": max_results},
			headers={"User-Agent": "Mozilla/5.0"},
			timeout=30,
		)
		resp.raise_for_status()

		from html.parser import HTMLParser

		class BaiduParser(HTMLParser):
			def __init__(self):
				super().__init__()
				self.results = []
				self._in_result = False
				self._current = {}

			def handle_starttag(self, tag, attrs):
				attrs_dict = dict(attrs)
				if tag == "a" and "data-tools" in attrs_dict:
					self._in_result = True
					self._current = {"url": attrs_dict.get("href", ""), "title": ""}

			def handle_data(self, data):
				if self._in_result:
					self._current["title"] += data

			def handle_endtag(self, tag):
				if tag == "a" and self._in_result:
					self._in_result = False
					if self._current.get("title"):
						self.results.append(self._current)

		parser = BaiduParser()
		parser.feed(resp.text)

		return json.dumps({"count": len(parser.results[:max_results]), "results": parser.results[:max_results]})
	except Exception as e:
		return json.dumps({"error": str(e)})
