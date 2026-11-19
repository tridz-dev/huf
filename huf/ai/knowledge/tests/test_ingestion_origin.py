import json

from huf.ai.knowledge.ingestion_origin import sanitize_source_config


def test_keeps_only_safe_keys():
	raw = json.dumps({"bucket": "b", "prefix": "p/", "secret_key": "x", "password": "y", "token": "t"})
	assert sanitize_source_config(raw) == {"bucket": "b", "prefix": "p/"}


def test_empty_and_bad_input():
	assert sanitize_source_config(None) is None
	assert sanitize_source_config("not json") is None
	assert sanitize_source_config({"password": "x"}) is None
