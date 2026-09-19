"""
Unit tests for the ST-R4.2 "latent guard" added to the five media handlers
in huf.ai.handlers.media (handle_generate_image, handle_ocr_document,
handle_generate_audio, handle_transcribe_audio, handle_generate_video).

IMPORTANT SCOPE NOTE (see WP-R4 / ST-R4.2, ST-R4.2b, Audit F-33, review item
21): Frappe's whitelisted-method dispatch does not await coroutines, so the
guard call inside these `async def` handlers never actually executes on a
real inbound HTTP request -- it is dead code on that path today. These tests
prove only that the guard's *internal* logic is correct when the coroutine
is driven directly (`asyncio.run(handle_xxx(...))`), i.e. that
`assert_agent_access` is called, with the right agent doc, before any
media-service logic runs. They do NOT prove the guard runs on a real
request, and F-33 must not be reported as closed on the strength of this
file alone -- see ST-R4.2b, which requires a live-bench probe (not run
here) to establish that.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_media_agent_access_guard
"""
import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.tests import _stub_env

_stub_env.install()

# _stub_env covers `frappe`, `frappe.utils` (now/add_to_date/etc.) and
# `frappe.tests`, but not `frappe.utils.file_manager` or `frappe._` --
# `huf.ai.audio_service` (imported transitively by
# huf.ai.handlers.media) needs both to import cleanly in a frappe-less
# environment. Only add what's missing; never clobber a real install.
frappe = sys.modules["frappe"]
if not hasattr(frappe, "_") or not callable(getattr(frappe, "_", None)):
    frappe._ = lambda s, *a, **kw: s
# `@frappe.whitelist()` must be a real passthrough decorator -- if it stays a
# MagicMock, `frappe.whitelist()(handle_generate_image)` returns a MagicMock
# instead of the coroutine function, and `handle_xxx(...)` no longer returns
# an awaitable at all.
if not isinstance(getattr(frappe, "whitelist", None), type(lambda: None)):
    frappe.whitelist = lambda *a, **kw: (lambda f: f)
if "frappe.utils.file_manager" not in sys.modules:
    file_manager_module = type(sys)("frappe.utils.file_manager")
    file_manager_module.save_file = MagicMock(name="save_file")
    sys.modules["frappe.utils.file_manager"] = file_manager_module
    frappe.utils.file_manager = file_manager_module

from huf.ai.handlers import media  # noqa: E402  (import after stubbing)


class _GuardFired(Exception):
    """Sentinel exception used to prove the guard ran before handler logic."""


def _make_agent_doc(name="test-agent"):
    return SimpleNamespace(name=name, owner="owner@example.com", allow_guest=False,
                            allowed_users=[], allowed_roles=[])


class MediaHandlerGuardTests(unittest.TestCase):
    """For each of the five media handlers: assert_agent_access is called,
    with a frappe.get_doc("Agent", <agent_name>)-resolved doc, as the very
    first thing the coroutine does -- before any media-service logic."""

    def _run_and_assert_guard_first(self, coro_factory, agent_name, extra_frappe_patches=None):
        agent_doc = _make_agent_doc(agent_name)

        with patch.object(media.frappe, "get_doc", return_value=agent_doc) as mock_get_doc, \
                patch.object(media.frappe, "session", SimpleNamespace(user="caller@example.com")), \
                patch(
                    "huf.ai.agent_access.assert_agent_access",
                    side_effect=_GuardFired,
                ) as mock_assert:
            extra_mocks = []
            if extra_frappe_patches:
                for target in extra_frappe_patches:
                    p = patch(target)
                    extra_mocks.append(p.start())
                    self.addCleanup(p.stop)

            with self.assertRaises(_GuardFired):
                asyncio.run(coro_factory())

            # The guard resolved the Agent doc and called assert_agent_access
            # with it before raising -- i.e. before the handler's try block
            # (and therefore before any media-service call) ever ran.
            mock_get_doc.assert_any_call("Agent", agent_name)
            mock_assert.assert_called_once()
            call_args = mock_assert.call_args
            self.assertIs(call_args.args[0], agent_doc)

            for m in extra_mocks:
                m.assert_not_called()

    def test_handle_generate_image_guard_runs_first(self):
        self._run_and_assert_guard_first(
            lambda: media.handle_generate_image(prompt="a cat", agent_name="agent-1"),
            "agent-1",
        )

    def test_handle_ocr_document_guard_runs_first(self):
        self._run_and_assert_guard_first(
            lambda: media.handle_ocr_document(file_id="file-1", agent_name="agent-2"),
            "agent-2",
        )

    def test_handle_generate_audio_guard_runs_first(self):
        self._run_and_assert_guard_first(
            lambda: media.handle_generate_audio(input="hello world", agent_name="agent-3"),
            "agent-3",
        )

    def test_handle_transcribe_audio_guard_runs_first(self):
        self._run_and_assert_guard_first(
            lambda: media.handle_transcribe_audio(file_id="file-2", agent_name="agent-4"),
            "agent-4",
        )

    def test_handle_generate_video_guard_runs_first(self):
        self._run_and_assert_guard_first(
            lambda: media.handle_generate_video(prompt="a dog running", agent_name="agent-5"),
            "agent-5",
        )

    def test_guard_allows_access_and_reaches_handler_logic_when_permitted(self):
        """Sanity check the inverse: when assert_agent_access does not raise,
        the coroutine proceeds past the guard into the handler's normal
        (agent-not-found) branch rather than being blocked spuriously."""
        agent_doc = _make_agent_doc("agent-6")
        with patch.object(media.frappe, "get_doc", return_value=agent_doc), \
                patch.object(media.frappe, "session", SimpleNamespace(user="caller@example.com")), \
                patch("huf.ai.agent_access.assert_agent_access", return_value=None) as mock_assert:
            result = asyncio.run(
                media.handle_generate_video(prompt="a cat", agent_name=None)
            )
            mock_assert.assert_called_once()
            self.assertFalse(result["success"])
            self.assertIn("Agent name not found in context", result["error"])


if __name__ == "__main__":
    unittest.main()
