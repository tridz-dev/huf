"""Unit tests for huf.ai.capability_discovery.resources and huf.ai.capability_discovery.ranking.

Run with:
    bench --site app-capability-discovery.local run-tests --app huf \
        --module huf.ai.capability_discovery.tests.test_resources
"""

import unittest
from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.capability_discovery import ranking
from huf.ai.capability_discovery.resources import get_app_resources, describe_resource


def _fake_meta(name, istable=0, issingle=0):
    """Lightweight stand-in for a frappe.get_meta(doctype) result.

    ranking.is_eligible_business_object / score_resource only touch
    .istable, .issingle, and .name, so a SimpleNamespace is sufficient
    and avoids any DB access for these pure-function tests.
    """
    return SimpleNamespace(name=name, istable=istable, issingle=issingle)


class TestIsEligibleBusinessObject(unittest.TestCase):
    """ranking.is_eligible_business_object should gate out child tables and singles."""

    def test_child_table_is_not_eligible(self):
        meta = _fake_meta("Foo Item", istable=1, issingle=0)
        self.assertFalse(ranking.is_eligible_business_object(meta))

    def test_single_doctype_is_not_eligible(self):
        meta = _fake_meta("Foo Settings", istable=0, issingle=1)
        self.assertFalse(ranking.is_eligible_business_object(meta))

    def test_regular_doctype_is_eligible(self):
        meta = _fake_meta("Foo", istable=0, issingle=0)
        self.assertTrue(ranking.is_eligible_business_object(meta))


class TestScoreResource(unittest.TestCase):
    """ranking.score_resource weighting per plan §6.2."""

    def test_exposed_doctype_gets_highest_score(self):
        exposed_meta = _fake_meta("Foo")
        exposed_score = ranking.score_resource(exposed_meta, is_exposed=True)

        # Even a submittable, well-linked, non-deprioritized DocType that is
        # NOT exposed should score lower than any exposed DocType, since
        # +100 for is_exposed dwarfs the +10 submittable bonus and the
        # link_count contribution (capped at 10).
        strong_unexposed_meta = _fake_meta("Bar")
        strong_unexposed_score = ranking.score_resource(
            strong_unexposed_meta, is_exposed=False, submittable=True, link_count=999
        )

        self.assertGreater(exposed_score, strong_unexposed_score)
        self.assertEqual(exposed_score, 100.0)

    def test_submittable_adds_bonus(self):
        meta = _fake_meta("Foo")
        base_score = ranking.score_resource(meta, submittable=False)
        submittable_score = ranking.score_resource(meta, submittable=True)
        self.assertEqual(submittable_score - base_score, 10)

    def test_deprioritized_name_pattern_subtracts(self):
        plain_meta = _fake_meta("Foo")
        settings_meta = _fake_meta("Foo Settings")

        plain_score = ranking.score_resource(plain_meta)
        settings_score = ranking.score_resource(settings_meta)

        self.assertEqual(plain_score - settings_score, 20)
        self.assertLess(settings_score, plain_score)

    def test_link_count_is_capped_at_ten(self):
        meta = _fake_meta("Foo")
        capped_score = ranking.score_resource(meta, link_count=50)
        exact_cap_score = ranking.score_resource(meta, link_count=10)
        self.assertEqual(capped_score, exact_cap_score)


class TestVisibilityForScore(unittest.TestCase):
    """ranking.visibility_for_score tier mapping."""

    def test_high_score_is_recommended(self):
        self.assertEqual(ranking.visibility_for_score(15), "recommended")
        self.assertEqual(ranking.visibility_for_score(100), "recommended")

    def test_mid_score_is_normal(self):
        self.assertEqual(ranking.visibility_for_score(0), "normal")
        self.assertEqual(ranking.visibility_for_score(14), "normal")

    def test_negative_score_is_advanced(self):
        self.assertEqual(ranking.visibility_for_score(-1), "advanced")
        self.assertEqual(ranking.visibility_for_score(-20), "advanced")

    def test_exposed_is_always_recommended_regardless_of_score(self):
        self.assertEqual(ranking.visibility_for_score(-20, is_exposed=True), "recommended")
        self.assertEqual(ranking.visibility_for_score(0, is_exposed=True), "recommended")
        self.assertEqual(ranking.visibility_for_score(100, is_exposed=True), "recommended")


class TestGetAppResources(FrappeTestCase):
    """resources.get_app_resources scope behavior against a real installed app."""

    def test_all_scope_returns_every_app_owned_doctype(self):
        modules = frappe.get_all("Module Def", filters={"app_name": "huf"}, pluck="name")
        self.assertTrue(modules, "expected the 'huf' app to own at least one Module Def")
        expected_doctypes = frappe.get_all(
            "DocType", filters={"module": ["in", modules]}, pluck="name"
        )

        all_resources = get_app_resources("huf", scope="all")

        self.assertEqual(
            {r["doctype"] for r in all_resources},
            set(expected_doctypes),
        )
        # scope="all" bypasses eligibility/visibility filtering entirely.
        self.assertGreaterEqual(len(all_resources), len(expected_doctypes))

    def test_recommended_scope_is_a_subset_of_all_scope(self):
        all_resources = get_app_resources("huf", scope="all")
        recommended_resources = get_app_resources("huf", scope="recommended")

        all_doctypes = {r["doctype"] for r in all_resources}
        recommended_doctypes = {r["doctype"] for r in recommended_resources}

        self.assertTrue(recommended_doctypes.issubset(all_doctypes))
        self.assertLessEqual(len(recommended_resources), len(all_resources))
        for resource in recommended_resources:
            self.assertEqual(resource["visibility"], "recommended")

    def test_invalid_scope_raises(self):
        with self.assertRaises(ValueError):
            get_app_resources("huf", scope="bogus")


class TestDescribeResource(FrappeTestCase):
    """resources.describe_resource enforces per-app ownership boundaries."""

    def test_raises_permission_error_for_doctype_owned_by_a_different_app(self):
        # "ToDo" is a core Frappe DocType (Module Def app_name="frappe"), so
        # describing it under the "huf" app must be rejected: an app cannot
        # reach across ownership boundaries to describe another app's
        # DocType, per plan §6.2.
        with self.assertRaises(frappe.PermissionError):
            describe_resource("huf", "ToDo")

    def test_describes_a_doctype_actually_owned_by_the_app(self):
        modules = frappe.get_all("Module Def", filters={"app_name": "huf"}, pluck="name")
        self.assertTrue(modules, "expected the 'huf' app to own at least one Module Def")
        owned_doctypes = frappe.get_all(
            "DocType", filters={"module": ["in", modules]}, pluck="name"
        )
        self.assertTrue(owned_doctypes)

        detail = describe_resource("huf", owned_doctypes[0])

        self.assertEqual(detail["doctype"], owned_doctypes[0])
        self.assertIn("generated_actions", detail)
        self.assertIn("generated_events", detail)
        self.assertIn("related_resources", detail)
