from unittest.mock import MagicMock

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.knowledge import context_builder as cb


def _fx_env(self):
	monkeypatch = self.monkeypatch
	calls = []
	allowed = set()
	fr = MagicMock()
	fr.has_permission.side_effect = lambda dt, ptype, name: name in allowed
	monkeypatch.setattr(cb, "frappe", fr)
	monkeypatch.setattr(
		cb,
		"get_mandatory_knowledge",
		lambda agent: [{"knowledge_source": n, "max_chunks": 3} for n in ("KS-A", "KS-B")],
	)

	def search(query, knowledge_source, top_k, ignore_permissions=False):
		calls.append((knowledge_source, ignore_permissions))
		return [{"text": f"secret-{knowledge_source}", "title": "t", "score": 1.0, "chunk_id": "1",
			"source": knowledge_source, "metadata": {}}]

	monkeypatch.setattr(cb, "knowledge_search", search)
	return allowed, calls, fr


class TestModule(SupportCase):
	def test_denied_source_not_injected(self):
		env = self.use(_fx_env)
		allowed, calls, _ = env
		r = cb.build_knowledge_context("ag", "q")
		assert r["context_text"] == "" and r["sources_used"] == []
		assert calls == []

	def test_allowed_source_injected(self):
		env = self.use(_fx_env)
		allowed, calls, _ = env
		allowed.add("KS-A")
		r = cb.build_knowledge_context("ag", "q")
		assert r["sources_used"] == ["KS-A"]
		assert "secret-KS-A" in r["context_text"] and "secret-KS-B" not in r["context_text"]

	def test_permitted_user_regression_all_sources(self):
		env = self.use(_fx_env)
		allowed, calls, _ = env
		allowed.update({"KS-A", "KS-B"})
		r = cb.build_knowledge_context("ag", "q")
		assert r["sources_used"] == ["KS-A", "KS-B"]
		assert "secret-KS-A" in r["context_text"] and "secret-KS-B" in r["context_text"]

	def test_never_ignores_permissions(self):
		env = self.use(_fx_env)
		allowed, calls, _ = env
		allowed.update({"KS-A", "KS-B"})
		cb.build_knowledge_context("ag", "q")
		assert calls and all(ign is False for _, ign in calls)

	def test_denial_log_has_no_content(self):
		env = self.use(_fx_env)
		_, _, fr = env
		cb.build_knowledge_context("ag", "q")
		msgs = [c.args[0] for c in fr.logger.return_value.debug.call_args_list]
		assert msgs and all("secret" not in m for m in msgs)
