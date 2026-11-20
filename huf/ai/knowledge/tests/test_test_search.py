"""Bench-less tests for knowledge_source.test_search input info (frappe mocked)."""

from unittest.mock import patch

from huf.huf.doctype.knowledge_source import knowledge_source as ks


def test_add_input_info_resolves_by_id_and_title():
	results = [
		{"title": "x", "metadata": {"input_id": "KI-1"}, "score": 1},
		{"title": "billing.md", "metadata": {}, "score": 0.5},
	]
	rows = [
		{"name": "KI-1", "title": "Refund policy", "file_name": "r.pdf"},
		{"name": "KI-2", "title": None, "file_name": "billing.md"},
	]
	with patch.object(ks.frappe, "get_all", return_value=rows):
		out = ks._add_input_info(results, "KS")
	assert out[0]["input_id"] == "KI-1" and out[0]["input_title"] == "Refund policy"
	assert out[1]["input_id"] == "KI-2" and out[1]["input_title"] == "billing.md"
	assert out[0]["score"] == 1


def test_add_input_info_empty():
	assert ks._add_input_info([], "KS") == []
