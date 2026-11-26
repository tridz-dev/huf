import pathlib


def test_url_extractor_maps_auth_errors():
	src = (pathlib.Path(__file__).parent.parent / "extractors" / "url.py").read_text()
	assert "status_code in (401, 403)" in src
	assert "AUTH_ERROR_MESSAGE" in src
	assert "publicly" in src
