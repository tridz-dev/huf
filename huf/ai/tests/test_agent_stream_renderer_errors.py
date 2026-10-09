"""Unit tests for huf.ai.agent_stream_renderer.AgentStreamRenderer error paths.

ST-R5.14: the agent lookup and permission check must happen first, and the
resulting error must be a uniform, generic message that never echoes back
the caller-supplied agent name -- so a caller cannot distinguish "agent does
not exist" from "agent exists but I lack permission" (SSE enumeration
oracle, F-40).

Follows huf.ai.tests.test_app_public_renderer's shape: pure unit tests
against mocked frappe APIs via renderer.__new__ (no live Frappe site/bench
required for construction), since the renderer under test only touches
frappe.get_doc / frappe.has_permission / frappe.form_dict.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_stream_renderer_errors
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.agent_stream_renderer import AgentStreamRenderer


def _make_renderer(agent_name="some-agent"):
    renderer = AgentStreamRenderer.__new__(AgentStreamRenderer)
    renderer.path = f"huf/stream/{agent_name}"
    renderer.http_status_code = 200
    return renderer


def _collect_sse_body(response):
    """Drain the werkzeug Response's generator into the SSE payload dict."""
    chunks = list(response.response)
    text = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks).decode()
    assert text.startswith("data: ")
    return json.loads(text[len("data: "):].strip())


class TestAgentStreamRendererErrorUniformity(unittest.TestCase):
    def _render(self, agent_name):
        renderer = _make_renderer(agent_name)
        with patch("huf.ai.agent_stream_renderer.frappe.form_dict", {"agent_name": agent_name, "prompt": "hi"}), \
                patch("huf.ai.agent_stream_renderer.frappe.request", new=MagicMock()) as mock_request:
            mock_request.method = "GET"
            return renderer._render_agent_stream(agent_name)

    def test_nonexistent_agent_does_not_leak_the_agent_name(self):
        with patch(
            "huf.ai.agent_stream_renderer.frappe.get_doc",
            side_effect=frappe.DoesNotExistError,
        ):
            response = self._render("does-not-exist-12345")

        body = _collect_sse_body(response)
        self.assertEqual(body["type"], "error")
        self.assertNotIn("does-not-exist-12345", body["error"])
        self.assertEqual(body["error"], "Agent not found")

    def test_existing_but_forbidden_agent_gets_identical_response(self):
        agent_doc = MagicMock()
        with patch("huf.ai.agent_stream_renderer.frappe.get_doc", return_value=agent_doc), \
                patch("huf.ai.agent_stream_renderer.frappe.has_permission", return_value=False):
            response = self._render("secret-agent-name")

        body = _collect_sse_body(response)
        self.assertEqual(body["type"], "error")
        self.assertNotIn("secret-agent-name", body["error"])
        self.assertEqual(body["error"], "Agent not found")

    def test_not_found_and_permission_denied_are_indistinguishable(self):
        """The two rejection reasons must produce byte-identical SSE bodies,
        not just 'a generic-looking message each'."""
        with patch(
            "huf.ai.agent_stream_renderer.frappe.get_doc",
            side_effect=frappe.DoesNotExistError,
        ):
            not_found_response = self._render("agent-a")

        agent_doc = MagicMock()
        with patch("huf.ai.agent_stream_renderer.frappe.get_doc", return_value=agent_doc), \
                patch("huf.ai.agent_stream_renderer.frappe.has_permission", return_value=False):
            forbidden_response = self._render("agent-b")

        self.assertEqual(
            _collect_sse_body(not_found_response),
            _collect_sse_body(forbidden_response),
        )

    def test_permission_check_happens_before_prompt_validation(self):
        """The agent lookup/permission check must run first: a request for a
        non-existent agent with no prompt still gets the generic
        'Agent not found' body, not the 'Prompt parameter required' body."""
        with patch(
            "huf.ai.agent_stream_renderer.frappe.get_doc",
            side_effect=frappe.DoesNotExistError,
        ):
            renderer = _make_renderer("missing-agent")
            with patch(
                "huf.ai.agent_stream_renderer.frappe.form_dict", {"agent_name": "missing-agent"}
            ), patch("huf.ai.agent_stream_renderer.frappe.request", new=MagicMock()) as mock_request:
                mock_request.method = "GET"
                response = renderer._render_agent_stream("missing-agent")

        body = _collect_sse_body(response)
        self.assertEqual(body["error"], "Agent not found")


if __name__ == "__main__":
    unittest.main()


class TestStreamErrorMessageSavedContract(unittest.TestCase):
    """Error chunks carry `message_saved` so clients know whether a retry would duplicate the user message."""

    def _collect(self, impl):
        import asyncio

        from huf.ai import agent_integration

        async def run():
            with patch.object(agent_integration, "_run_agent_stream_impl", impl), \
                    patch.object(agent_integration.frappe, "log_error"):
                return [c async for c in agent_integration.run_agent_stream("a", "p")]

        return asyncio.new_event_loop().run_until_complete(run())

    def test_rejection_before_persist_is_not_saved(self):
        async def impl(*a, _state=None, **k):
            yield {"type": "error", "error": "Agent 'a' is disabled."}

        chunks = self._collect(impl)
        self.assertIs(chunks[0]["message_saved"], False)

    def test_error_after_persist_is_saved(self):
        async def impl(*a, _state=None, **k):
            _state["message_saved"] = True
            yield {"type": "error", "error": "provider failed"}

        self.assertIs(self._collect(impl)[0]["message_saved"], True)

    def test_exception_raised_after_persist_in_first_anext_is_saved(self):
        async def impl(*a, _state=None, **k):
            _state["message_saved"] = True
            raise RuntimeError("boom")
            yield  # pragma: no cover

        chunks = self._collect(impl)
        self.assertEqual(chunks[0]["type"], "error")
        self.assertIs(chunks[0]["message_saved"], True)

    def test_exception_before_persist_is_not_saved(self):
        async def impl(*a, _state=None, **k):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        self.assertIs(self._collect(impl)[0]["message_saved"], False)

    def test_raw_exception_text_is_not_sent_to_client(self):
        async def impl(*a, _state=None, **k):
            raise RuntimeError("Table `tabAgent Run` doesn't exist (1146) secret-sql")
            yield  # pragma: no cover

        chunks = self._collect(impl)
        self.assertEqual(chunks[0]["error"], "The request could not be completed. Please try again.")
        self.assertNotIn("secret-sql", json.dumps(chunks))

    def test_validation_error_message_is_kept(self):
        async def impl(*a, _state=None, **k):
            raise frappe.ValidationError("Prompt is too long")
            yield  # pragma: no cover

        self.assertEqual(self._collect(impl)[0]["error"], "Prompt is too long")

    def test_abandon_unsaved_run_marks_failed_and_frees_idempotency_key(self):
        from huf.ai import agent_integration as ai

        with patch.object(ai.frappe.db, "rollback") as rb, \
                patch.object(ai.frappe.db, "set_value") as sv, \
                patch.object(ai.frappe.db, "commit") as cm:
            ai._abandon_unsaved_run("RUN-1", RuntimeError("add_message failed"))
        rb.assert_called_once()
        args = sv.call_args[0]
        self.assertEqual(args[:2], ("Agent Run", "RUN-1"))
        self.assertEqual(args[2]["status"], "Failed")
        self.assertIsNone(args[2]["idempotency_key"])
        cm.assert_called_once()

    def test_renderer_rejection_chunk_is_not_saved(self):
        renderer = _make_renderer("x")
        self.assertIs(_collect_sse_body(renderer._sse_error_response("nope"))["message_saved"], False)
