import logging

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.gateways.slack import files as sf

TOKEN = "xoxb-SECRET-TOKEN-123"
GOOD = "https://files.slack.com/files-pri/T1-F1/doc.pdf"


class Resp:
	def __init__(self, status=200, ctype="application/pdf", chunks=(b"data",)):
		self.status_code = status
		self.headers = {"Content-Type": ctype}
		self._chunks = chunks
		self.closed = False

	def iter_content(self, chunk_size=0):
		yield from self._chunks

	def close(self):
		self.closed = True


class Env:
	def __init__(self, resp=None, raises=None):
		self.resp, self.raises, self.calls, self.saved = resp or Resp(), raises, [], []

	def get(self, url, **kw):
		self.calls.append((url, kw))
		if self.raises:
			raise self.raises
		return self.resp

	def save(self, name, content, **kw):
		self.saved.append((name, content, kw))
		return "FILE-0001"


def run(info, env=None, **over):
	env = env or Env()
	info = {"id": "F1", "name": "doc.pdf", "url_private_download": GOOD, **info}
	info = {k: v for k, v in info.items() if v is not None}
	return sf.download_slack_file(info, TOKEN, http_get=env.get, save_file=env.save), env


class TestModule(SupportCase):
	def test_success_private_and_headers(self):
		out, env = run({})
		assert out["file_doc"] == "FILE-0001" and out["mime_type"] == "application/pdf"
		assert env.saved[0][2]["is_private"] is True
		url, kw = env.calls[0]
		assert kw["allow_redirects"] is False and kw["stream"] is True
		assert isinstance(kw["timeout"], tuple) and len(kw["timeout"]) == 2
		assert kw["headers"]["Authorization"] == f"Bearer {TOKEN}"
		assert env.resp.closed

	def test_fallback_to_url_private(self):
		out, env = run({"url_private_download": None, "url_private": GOOD})
		assert out and env.calls[0][0] == GOOD

	def test_forbidden_urls(self):
		for url in [
	"https://files.slack.com.evil.com/x", "http://files.slack.com/x", "https://evil.com/x",
	"https://evil.com/files.slack.com", "https://files.slack.com@evil.com/x",
	"https://evil.com#@files.slack.com/", "ftp://files.slack.com/x", "", "not a url",
]:
			with self.subTest(url=url):
				out, env = run({"url_private_download": url})
				assert out is None and env.calls == []

	def test_no_url_at_all(self):
		out, env = run({"url_private_download": None})
		assert out is None and env.calls == []

	def test_redirect_rejected(self):
		out, env = run({}, Env(Resp(status=302)))
		assert out is None and env.saved == []

	def test_declared_oversize_no_request(self):
		out, env = run({"size": 20 * 1024 * 1024 + 1})
		assert out is None and env.calls == []

	def test_streamed_oversize_with_lying_size(self):
		big = [b"x" * (1024 * 1024)] * 21
		out, env = run({"size": 10}, Env(Resp(chunks=big)))
		assert out is None and env.saved == []

	def test_exact_cap_ok(self):
		out, _ = run({}, Env(Resp(chunks=[b"x" * (20 * 1024 * 1024)])))
		assert out and out["size"] == 20 * 1024 * 1024

	def test_html_rejected(self):
		out, env = run({}, Env(Resp(ctype="text/html; charset=utf-8")))
		assert out is None and env.saved == []

	def test_bad_mime(self):
		for ctype in ["application/x-msdownload", "application/zip", "application/javascript", "image/../x"]:
			with self.subTest(ctype=ctype):
				out, _ = run({}, Env(Resp(ctype=ctype)))
				assert out is None

	def test_allowed_mime(self):
		for ctype in ["image/png", "audio/mpeg", "video/mp4", "text/plain; charset=utf-8", "text/csv",
	"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
			with self.subTest(ctype=ctype):
				out, _ = run({}, Env(Resp(ctype=ctype)))
				assert out

	def test_non_200_and_empty_body(self):
		assert run({}, Env(Resp(status=403)))[0] is None
		assert run({}, Env(Resp(chunks=[])))[0] is None

	def test_sanitize_filename(self):
		for raw, expected in [
	("../../etc/passwd", "passwd"), ("a\\b\\c.txt", "c.txt"), ("ev\x00il\n.png", "evil.png"),
	("..", "slack-file"), ("", "slack-file"), (".hidden", "hidden"),
]:
			with self.subTest(raw=raw, expected=expected):
				assert sf.sanitize_filename(raw) == expected

	def test_filename_length_and_saved_name(self):
		assert len(sf.sanitize_filename("a" * 500 + ".pdf")) <= 120
		out, env = run({"name": "../../x/evil\x07.pdf"})
		assert env.saved[0][0] == "evil.pdf" and out["filename"] == "evil.pdf"

	def test_non_dict_or_missing_token(self):
		assert sf.download_slack_file("x", TOKEN) is None
		assert sf.download_slack_file({"url_private": GOOD}, "") is None

	def test_token_never_logged_or_raised(self):
		caplog = self.caplog
		caplog.set_level(logging.DEBUG)
		boom = RuntimeError(f"Authorization: Bearer {TOKEN}")
		cases = [Env(raises=boom), Env(Resp(status=403)), Env(Resp(ctype="text/html")), Env(Resp(chunks=[b"x" * (21 << 20)]))]
		for env in cases:
			out, _ = run({}, env)
			assert out is None
		run({"url_private_download": "https://evil.com/x"})
		assert TOKEN not in caplog.text
		assert all(TOKEN not in str(r.args) + r.getMessage() for r in caplog.records)
		assert "F1" in caplog.text

	def test_save_failure_returns_none(self):
		env = Env()
		env.save = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(TOKEN))
		out, _ = run({}, env)
		assert out is None

	def test_port_and_userinfo_rejected(self):
		for url in [
	"https://files.slack.com:8443/x", "https://user@files.slack.com/x", "https://user:pw@files.slack.com/x",
	"https://:pw@files.slack.com/x",
]:
			with self.subTest(url=url):
				out, env = run({"url_private_download": url})
				assert out is None and env.calls == []

	def test_explicit_443_allowed(self):
		out, env = run({"url_private_download": "https://files.slack.com:443/x.pdf"})
		assert out and env.calls

	def test_total_deadline_enforced_in_stream(self):
		monkeypatch = self.monkeypatch
		clock = iter([0, 1, 2, 31, 32, 33, 34])
		monkeypatch.setattr(sf.time, "monotonic", lambda: next(clock))
		out, env = run({}, Env(Resp(chunks=[b"a", b"b", b"c", b"d"])))
		assert out is None and env.saved == []

	def test_octet_stream_falls_back_to_file_mimetype(self):
		for ctype in ["application/octet-stream", "", None]:
			with self.subTest(ctype=ctype):
				resp = Resp(ctype=ctype or "")
				if ctype is None:
					resp.headers = {}
				out, _ = run({"mimetype": "application/pdf"}, Env(resp))
				assert out and out["mime_type"] == "application/pdf"

	def test_octet_stream_with_disallowed_declared_mime_rejected(self):
		out, _ = run({"mimetype": "application/zip"}, Env(Resp(ctype="application/octet-stream")))
		assert out is None
		out, _ = run({}, Env(Resp(ctype="application/octet-stream")))
		assert out is None

	def test_force_download_content_type_falls_back_to_declared_mime(self):
		class Resp:
			status_code = 200
			headers = {"Content-Type": "application/force-download"}

			def iter_content(self, chunk_size=0):
				yield b"hello"

			def close(self):
				pass

		saved = []
		out = sf.download_slack_file(
			{"id": "F1", "name": "n.txt", "mimetype": "text/plain", "size": 5,
				"url_private_download": "https://files.slack.com/files-pri/T-F/n.txt"},
			"xoxb-t", http_get=lambda *a, **k: Resp(), save_file=lambda n, c, is_private=True: saved.append(n) or "FILE-1")
		assert out and out["mime_type"] == "text/plain" and saved == ["n.txt"]
