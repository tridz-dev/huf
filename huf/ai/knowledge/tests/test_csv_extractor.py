import importlib.util
import pathlib
import sys
import types
from dataclasses import dataclass


def _load():
	pkg = types.ModuleType("huf.ai.knowledge.extractors")

	@dataclass
	class ExtractedText:
		text: str
		title: str = None
		metadata: dict = None

	class TextExtractor:
		pass

	pkg.ExtractedText = ExtractedText
	pkg.TextExtractor = TextExtractor
	pkg.__path__ = []
	sys.modules["huf.ai.knowledge.extractors"] = pkg
	path = pathlib.Path(__file__).parent.parent / "extractors" / "csv_extractor.py"
	spec = importlib.util.spec_from_file_location("huf.ai.knowledge.extractors.csv_extractor", path)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


m = _load()


def _extract(tmp_path, raw: bytes):
	p = tmp_path / "d.csv"
	p.write_bytes(raw)
	return m.CSVExtractor().extract(str(p)).text


def test_headers_kept_per_row(tmp_path):
	rows = "name,city\n" + "\n".join(f"n{i},c{i}" for i in range(500))
	text = _extract(tmp_path, rows.encode())
	assert "name: n499\ncity: c499" in text


def test_latin1(tmp_path):
	assert "caf\xe9" in _extract(tmp_path, "a,b\ncaf\xe9,1\n".encode("latin-1"))


def test_utf16_bom(tmp_path):
	assert "x: ü" in _extract(tmp_path, "x,y\nü,2\n".encode("utf-16"))


def test_empty_and_header_only(tmp_path):
	assert _extract(tmp_path, b"") == ""
	assert _extract(tmp_path, b"a,b\n") == "a\nb"


def test_safety_includes_csv():
	src = (pathlib.Path(__file__).parent.parent / "sources" / "safety.py").read_text()
	assert '".csv"' in src
