# ruff: noqa: S101
from huf.ai.external.oauth import build_metadata, challenge_header, metadata_url, resource_url

BASE = "https://huf.example.com/"


def test_urls_have_no_double_slash():
	assert resource_url(BASE) == "https://huf.example.com/api/method/huf.ai.external.gateway.mcp"
	assert metadata_url(BASE).startswith("https://huf.example.com/api/method/")


def test_challenge_points_at_metadata():
	assert challenge_header(BASE) == f'Bearer resource_metadata="{metadata_url(BASE)}"'


def test_metadata_shape():
	doc = build_metadata(BASE, ["all"])
	assert doc["resource"] == resource_url(BASE)
	assert doc["authorization_servers"] == ["https://huf.example.com"]
	assert doc["bearer_methods_supported"] == ["header"]
	assert doc["scopes_supported"] == ["all"]
	assert "scopes_supported" not in build_metadata(BASE)
