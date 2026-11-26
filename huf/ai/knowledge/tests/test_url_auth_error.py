import pathlib
import unittest


class TestURLAuthError(unittest.TestCase):
	def test_url_extractor_maps_auth_errors(self):
		src = (pathlib.Path(__file__).parent.parent / "extractors" / "url.py").read_text()
		self.assertIn(("status_code in (401, 403)"), (src))
		self.assertIn(("AUTH_ERROR_MESSAGE"), (src))
		self.assertIn(("publicly"), (src))
