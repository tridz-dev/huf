"""
Unit tests for huf.ai.app_public_renderer.HufAppPublicRenderer.

No existing page-renderer test exists in huf/ai/tests/ to model this on, so
these follow huf.ai.tests.test_agent_access's shape instead (pure unit tests
against mocked frappe APIs, no live Frappe site/bench required) rather than
huf.ai.tests.test_app_builder_tools's IntegrationTestCase shape, since the
renderer under test only touches frappe.db.get_value/frappe.get_doc and the
already-unit-tested check_agent_access — no DB writes are needed.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_app_public_renderer
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.app_public_renderer import HufAppPublicRenderer


def _make_agent(allow_guest=False):
    return SimpleNamespace(
        owner="owner@example.com",
        allow_guest=allow_guest,
        allowed_users=[],
        allowed_roles=[],
    )


class TestHufAppPublicRenderer(unittest.TestCase):
    def _make_renderer(self, alias="my-app"):
        renderer = HufAppPublicRenderer.__new__(HufAppPublicRenderer)
        renderer.path = f"huf/apps/{alias}"
        renderer.http_status_code = 200
        return renderer

    def test_can_render_matches_apps_prefix(self):
        renderer = self._make_renderer("my-app")
        self.assertTrue(renderer.can_render())

    def test_can_render_ignores_unrelated_paths(self):
        renderer = self._make_renderer("my-app")
        renderer.path = "huf/stream/some-agent"
        self.assertFalse(renderer.can_render())

    def test_not_found_when_app_is_not_public(self):
        """is_public=0 -> the get_value filter itself excludes the row,
        so this looks identical to a nonexistent alias."""
        renderer = self._make_renderer("private-app")
        with patch("huf.ai.app_public_renderer.frappe.db.get_value", return_value=None):
            with patch("huf.ai.app_public_renderer.frappe.form_dict", {}):
                with self.assertRaises(frappe.PageDoesNotExistError):
                    renderer.render()

    def test_not_found_when_public_but_agent_denies_guest(self):
        """Anti-enumeration: public app + allow_guest=0 on the Agent must
        raise the exact same PageDoesNotExistError as the not-public case
        above — never a distinct error that would leak the app's existence."""
        renderer = self._make_renderer("public-but-denied")
        app_row = SimpleNamespace(name="APP-1", agent="AGENT-1")
        agent_doc = _make_agent(allow_guest=False)

        with patch("huf.ai.app_public_renderer.frappe.form_dict", {}), \
                patch("huf.ai.app_public_renderer.frappe.db.get_value", return_value=app_row), \
                patch("huf.ai.app_public_renderer.frappe.get_doc", return_value=agent_doc):
            with self.assertRaises(frappe.PageDoesNotExistError):
                renderer.render()

    def test_granted_when_public_and_agent_allows_guest(self):
        renderer = self._make_renderer("public-and-allowed")
        app_row = SimpleNamespace(name="APP-1", agent="AGENT-1")
        agent_doc = _make_agent(allow_guest=True)
        sentinel_response = object()

        with patch("huf.ai.app_public_renderer.frappe.form_dict", {}), \
                patch("huf.ai.app_public_renderer.frappe.db.get_value", return_value=app_row), \
                patch("huf.ai.app_public_renderer.frappe.get_doc", return_value=agent_doc), \
                patch("huf.ai.app_public_renderer.TemplatePage") as mock_template_page:
            mock_template_page.return_value.render.return_value = sentinel_response
            result = renderer.render()

        mock_template_page.assert_called_once_with("huf", renderer.http_status_code)
        self.assertIs(result, sentinel_response)

    def test_same_not_found_error_type_across_both_denial_reasons(self):
        """Belt-and-suspenders: assert both rejection paths raise the exact
        same exception class, not just 'an error'."""
        renderer_a = self._make_renderer("not-public")
        renderer_b = self._make_renderer("public-but-denied")

        with patch("huf.ai.app_public_renderer.frappe.form_dict", {}):
            with patch("huf.ai.app_public_renderer.frappe.db.get_value", return_value=None):
                with self.assertRaises(frappe.PageDoesNotExistError) as ctx_a:
                    renderer_a.render()

            app_row = SimpleNamespace(name="APP-1", agent="AGENT-1")
            agent_doc = _make_agent(allow_guest=False)
            with patch("huf.ai.app_public_renderer.frappe.db.get_value", return_value=app_row), \
                    patch("huf.ai.app_public_renderer.frappe.get_doc", return_value=agent_doc):
                with self.assertRaises(frappe.PageDoesNotExistError) as ctx_b:
                    renderer_b.render()

        self.assertIs(type(ctx_a.exception), type(ctx_b.exception))


if __name__ == "__main__":
    unittest.main()
