# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for ST-R5.4: pagination on
`huf.api.v1.endpoints.agents.handle_list_agents` / `_list_accessible_agents`.

Covers:
- A single `frappe.get_all` call is used to fetch the page (no per-row
  `get_doc`, i.e. no N+1).
- Paginating through a mocked set of 100 Agent rows with limit=20 returns
  all 100 rows across pages with no duplicates.
- `has_more` is True for full pages and False for the final partial/empty
  page.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_v1_agents_pagination.py -v
"""

import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.api.v1.endpoints import agents as agents_endpoint  # noqa: E402


class _FakeRow(dict):
    """Minimal stand-in for frappe's `_dict`: supports both attribute and
    item access/assignment, which is what `frappe.get_all(..., fields=[...])`
    rows and `_list_accessible_agents`'s `row["allowed_users"] = ...` need."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)

    def __setattr__(self, key, value):
        self[key] = value


def _make_rows(count):
    rows = []
    for i in range(count):
        rows.append(
            _FakeRow(
                name=f"AGENT-{i:03d}",
                agent_name=f"Agent {i}",
                description="",
                agent_modality="text",
                voice_enabled=0,
                allow_file_upload=0,
                run_immediately=0,
                owner="owner@example.com",
                allow_guest=0,
            )
        )
    return rows


class TestAgentsPagination(unittest.TestCase):
    def setUp(self):
        self.all_rows = _make_rows(100)

        def fake_get_all(doctype, filters=None, fields=None, order_by=None, limit_page_length=None, limit_start=0):
            if doctype == "Agent":
                start = limit_start or 0
                end = start + (limit_page_length or len(self.all_rows))
                return self.all_rows[start:end]
            # Agent User / Agent Role child-table bulk fetches: no restrictions configured.
            return []

        self.get_all_mock = MagicMock(side_effect=fake_get_all)
        patcher = patch.object(agents_endpoint.frappe, "get_all", self.get_all_mock)
        self.addCleanup(patcher.stop)
        patcher.start()

        access_patcher = patch.object(agents_endpoint, "check_agent_access", return_value=True)
        self.addCleanup(access_patcher.stop)
        access_patcher.start()

    def test_single_get_all_call_per_page_no_n_plus_one(self):
        agents_endpoint._list_accessible_agents("user@example.com", limit=20, offset=0)
        # One call for the Agent page, two for the child-table bulk fetches
        # (allowed_users, allowed_roles) - never one `get_doc` per row.
        self.assertEqual(self.get_all_mock.call_count, 3)

    def test_paginate_through_100_agents_returns_all_with_no_duplicates(self):
        seen_names = []
        offset = 0
        limit = 20
        has_more = True
        pages = 0

        while has_more:
            rows, has_more = agents_endpoint._list_accessible_agents("user@example.com", limit, offset)
            seen_names.extend(row.name for row in rows)
            offset += limit
            pages += 1
            self.assertLess(pages, 10, "pagination did not terminate")

        self.assertEqual(len(seen_names), 100)
        self.assertEqual(len(set(seen_names)), 100, "duplicate rows returned across pages")

    def test_has_more_true_on_full_page_false_on_final_page(self):
        _, has_more_page1 = agents_endpoint._list_accessible_agents("user@example.com", 20, 0)
        self.assertTrue(has_more_page1)

        # offset=90, limit=20 against 100 total rows returns a partial (10-row)
        # final page - fewer rows than requested signals no further pages.
        _, has_more_last = agents_endpoint._list_accessible_agents("user@example.com", 20, 90)
        self.assertFalse(has_more_last)

    def test_handle_list_agents_response_shape(self):
        with patch.object(agents_endpoint.frappe, "local", MagicMock(form_dict={"limit": "20", "offset": "0"})):
            with patch("huf.api.v1.endpoints.agents.require_scope"):
                context = SimpleNamespace(user="user@example.com")
                result = agents_endpoint.handle_list_agents(context)

        self.assertEqual(len(result["agents"]), 20)
        self.assertTrue(result["has_more"])
        self.assertEqual(result["cursor"], 20)

    def test_handle_list_agents_limit_is_capped_at_server_max(self):
        with patch.object(
            agents_endpoint.frappe, "local", MagicMock(form_dict={"limit": "9999", "offset": "0"})
        ):
            with patch("huf.api.v1.endpoints.agents.require_scope"):
                context = SimpleNamespace(user="user@example.com")
                result = agents_endpoint.handle_list_agents(context)

        self.assertLessEqual(len(result["agents"]), agents_endpoint.MAX_PAGE_LENGTH)


if __name__ == "__main__":
    unittest.main()
