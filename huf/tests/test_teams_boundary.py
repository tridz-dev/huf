import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAT = re.compile(r"microsoft[_ ]?teams|msteams|botframework|\bTeamsAdapter\b|gateway_adapters\.teams", re.I)
ALLOWED_NAMES = {"registered.py", "provider_ids.py", "install.py"}
# remove entries as owning WPs finish (T5 deletes the first two)
KNOWN = {
	"huf/ai/gateway_webhook.py",
	"huf/ai/tools/teams_webhook.py",
	"huf/ai/tools/gateway_pairing_tools.py",
	"huf/huf/doctype/gateway/gateway.py",
}


def _allowed(rel):
	parts = rel.split("/")
	name = parts[-1]
	return (
		rel.startswith("huf/ai/teams/")
		or (rel.startswith("huf/ai/gateway_adapters/") and name.startswith("teams") and len(parts) == 4)
		or name in ALLOWED_NAMES
		or name.startswith("test_")
		or any(p in ("tests", "patches") for p in parts[:-1])
	)


class TestTeamsBoundary(unittest.TestCase):
	def test_no_teams_logic_in_core(self):
		bad = []
		for p in (ROOT / "huf").rglob("*.py"):
			rel = p.relative_to(ROOT).as_posix()
			if _allowed(rel) or rel in KNOWN:
				continue
			if PAT.search(p.read_text(errors="ignore")):
				bad.append(rel)
		self.assertEqual(bad, [], "Teams logic outside the allowed modules")
