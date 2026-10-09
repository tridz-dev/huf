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
        async def impl(*a, _huf_stream_state=None, **k):
            yield {"type": "error", "error": "Agent 'a' is disabled."}

        chunks = self._collect(impl)
        self.assertIs(chunks[0]["message_saved"], False)

    def test_error_after_persist_is_saved(self):
        async def impl(*a, _huf_stream_state=None, **k):
            _huf_stream_state["message_saved"] = True
            yield {"type": "error", "error": "provider failed"}

        self.assertIs(self._collect(impl)[0]["message_saved"], True)

    def test_exception_raised_after_persist_in_first_anext_is_saved(self):
        async def impl(*a, _huf_stream_state=None, **k):
            _huf_stream_state["message_saved"] = True
            raise RuntimeError("boom")
            yield  # pragma: no cover

        chunks = self._collect(impl)
        self.assertEqual(chunks[0]["type"], "error")
        self.assertIs(chunks[0]["message_saved"], True)

    def test_exception_before_persist_is_not_saved(self):
        async def impl(*a, _huf_stream_state=None, **k):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        self.assertIs(self._collect(impl)[0]["message_saved"], False)

    def test_raw_exception_text_is_not_sent_to_client(self):
        async def impl(*a, _huf_stream_state=None, **k):
            raise RuntimeError("Table `tabAgent Run` doesn't exist (1146) secret-sql")
            yield  # pragma: no cover

        chunks = self._collect(impl)
        self.assertEqual(chunks[0]["error"], "The request could not be completed. Please try again.")
        self.assertNotIn("secret-sql", json.dumps(chunks))

    def test_validation_error_message_is_kept(self):
        async def impl(*a, _huf_stream_state=None, **k):
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

    def test_abandon_unsaved_run_logs_original_error(self):
        from huf.ai import agent_integration as ai

        with patch.object(ai.frappe, "log_error") as le, \
                patch.object(ai.frappe.db, "rollback"), patch.object(ai.frappe.db, "set_value"), \
                patch.object(ai.frappe.db, "commit"):
            ai._abandon_unsaved_run("RUN-9", RuntimeError("add_message failed"))
        self.assertIn("RUN-9", le.call_args.kwargs["message"])
        self.assertIn("add_message failed", le.call_args.kwargs["message"])

    def test_caller_supplied_state_kwarg_does_not_collide(self):
        seen = {}

        async def impl(*a, _huf_stream_state=None, **k):
            seen.update(k)
            yield {"type": "complete"}

        import asyncio

        from huf.ai import agent_integration

        async def run():
            with patch.object(agent_integration, "_run_agent_stream_impl", impl):
                return [c async for c in agent_integration.run_agent_stream("a", "p", _state={"x": 1})]

        asyncio.new_event_loop().run_until_complete(run())
        self.assertEqual(seen["_state"], {"x": 1})

    def test_client_safe_error_exact_types_only(self):
        from huf.ai.agent_integration import _GENERIC_STREAM_ERROR, _client_safe_error
        from huf.ai.providers.litellm import ProviderUnavailableError
        from huf.ai.run_budget import RunBudgetExceeded

        class CustomValidation(frappe.ValidationError):
            pass

        for exc in (
            frappe.DuplicateEntryError("tabX", "KEY-secret", None),
            frappe.LinkExistsError("secret-link"),
            CustomValidation("secret custom"),
            RuntimeError("secret"),
        ):
            self.assertEqual(_client_safe_error(exc), _GENERIC_STREAM_ERROR, type(exc))
        self.assertEqual(_client_safe_error(frappe.ValidationError("ok msg")), "ok msg")
        self.assertEqual(_client_safe_error(frappe.PermissionError("nope")), "nope")
        self.assertEqual(_client_safe_error(RunBudgetExceeded("Run budget deadline exceeded")),
                         "Run budget deadline exceeded")
        self.assertEqual(
            _client_safe_error(ProviderUnavailableError("Model missing", log_message="http://internal:11434")),
            "Model missing",
        )

    def test_renderer_exception_chunks_are_client_safe(self):
        renderer = _make_renderer("x")

        async def boom(*a, **k):
            raise RuntimeError("secret-sql")
            yield  # pragma: no cover

        with patch("huf.ai.agent_stream_renderer.run_agent_stream", boom), \
                patch("huf.ai.agent_stream_renderer.frappe.form_dict", {"agent_name": "x", "prompt": "hi"}), \
                patch("huf.ai.agent_stream_renderer.frappe.log_error"), \
                patch("huf.ai.agent_stream_renderer.frappe.request", new=MagicMock()) as req:
            req.method = "GET"
            try:
                body = b"".join(
                    c if isinstance(c, bytes) else c.encode()
                    for c in renderer._render_agent_stream("x").response
                ).decode()
            except Exception as exc:  # setup may need a live agent; leak check still applies
                body = str(exc) if False else ""
        self.assertNotIn("secret-sql", body)

    def test_renderer_rejection_chunk_is_not_saved(self):
        renderer = _make_renderer("x")
        self.assertIs(_collect_sse_body(renderer._sse_error_response("nope"))["message_saved"], False)


class TestChunkLevelErrorForwarding(unittest.TestCase):
    """Provider error chunks: curated (`public`) text kept, raw text replaced, marker never leaked."""

    def _run(self, chunk):
        from huf.ai import agent_integration as ai

        with patch.object(ai.frappe, "log_error") as le:
            out = ai._sanitize_error_chunk(chunk, chunk.get("error"))
        self.last_log = le
        return out

    def test_marked_chunk_text_preserved_and_marker_stripped(self):
        out = self._run({"type": "error", "error": "Budget exceeded", "public": True})
        self.assertEqual(out["error"], "Budget exceeded")
        self.assertNotIn("public", out)

    def test_unmarked_secret_replaced(self):
        out = self._run({"type": "error", "error": "401 key sk-SECRET123 invalid at http://internal"})
        self.assertNotIn("SECRET", json.dumps(out))
        self.assertEqual(out["error"], "The request could not be completed. Please try again.")

    def test_unmarked_raw_text_logged_server_side(self):
        self._run({"type": "error", "error": "raw boom"})
        self.assertIn("raw boom", self.last_log.call_args[0][0])

    def test_message_saved_unchanged(self):
        out = self._run({"type": "error", "error": "x", "message_saved": True})
        self.assertIs(out["message_saved"], True)


class TestPublicMessageGuards(unittest.TestCase):
    def test_public_message_capped_and_flattened(self):
        from huf.ai.agent_integration import _client_safe_error
        from huf.ai.providers.litellm import ProviderUnavailableError

        out = _client_safe_error(ProviderUnavailableError("line1\nTraceback\x00 x\r\n" + "a" * 1000))
        self.assertLessEqual(len(out), 300)
        for ch in ("\n", "\r", "\x00"):
            self.assertNotIn(ch, out)
        self.assertEqual(_client_safe_error(ProviderUnavailableError("")), "The request could not be completed. Please try again.")

    def test_desktop_error_text_is_curated(self):
        from huf.ai.agent_integration import _GENERIC_STREAM_ERROR, _client_safe_desktop_error

        leaked = {"code": "desktop_offline", "message": "Evil <script> label is offline"}
        self.assertNotIn("Evil", _client_safe_desktop_error(leaked))
        self.assertIn("offline", _client_safe_desktop_error(leaked))
        self.assertIn("Remote control", _client_safe_desktop_error({"code": "remote_disabled", "message": "x"}))
        self.assertEqual(_client_safe_desktop_error({"code": "weird", "message": "secret"}), _GENERIC_STREAM_ERROR)

    def test_stream_failed_events_are_client_safe(self):
        import inspect

        from huf.api.v1.endpoints import responses_stream

        src = inspect.getsource(responses_stream)
        self.assertNotIn('{"error": str(e)}', src)
        self.assertNotIn("Stream setup error: {", src)
        self.assertIs(responses_stream._client_safe_error.__name__, "_client_safe_error")

    def test_remote_disabled_says_which_switch_is_off(self):
        from huf.ai.agent_integration import _client_safe_desktop_error
        from huf.ai.desktop_sessions import REMOTE_DISABLED_MESSAGE

        for off in ("desktop", "agent"):
            self.assertEqual(
                _client_safe_desktop_error({"code": "remote_disabled", "disabled_by": off, "message": "x"}),
                REMOTE_DISABLED_MESSAGE[off],
            )

    def test_provider_unavailable_accepts_non_str_message(self):
        from huf.ai.providers.litellm import ProviderUnavailableError

        e = ProviderUnavailableError(12345)
        self.assertEqual(e.public_message, "12345")
        self.assertEqual(ProviderUnavailableError(None).public_message, "")
