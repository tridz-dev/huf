# Copyright (c) 2026, Huf and Contributors
# See license.txt

"""
Unit tests for AI Model modality validation and link query filtering
(huf/huf/doctype/ai_model/ai_model.py).

These tests mock frappe so the modality parsing and SQL query generation
can be exercised without a full Frappe bench.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock


class ThrowError(Exception):
    """Stand-in for frappe.throw so tests can assert on thrown messages."""


def _throw(msg, *args, **kwargs):
    raise ThrowError(str(msg))


# Set up frappe mock before importing ai_model
frappe_mock = types.ModuleType("frappe")
frappe_mock._ = lambda x, *a, **k: x
frappe_mock.throw = MagicMock(side_effect=_throw)
frappe_mock.whitelist = lambda *a, **k: (lambda f: f)
frappe_mock.db = MagicMock()

# Document stub
class Document:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)

frappe_mock.model = types.ModuleType("frappe.model")
frappe_mock.model.document = types.ModuleType("frappe.model.document")
frappe_mock.model.document.Document = Document

sys.modules["frappe"] = frappe_mock
sys.modules["frappe.model"] = frappe_mock.model
sys.modules["frappe.model.document"] = frappe_mock.model.document

from huf.huf.doctype.ai_model.ai_model import (  # noqa: E402
    MODEL_MODALITY_OPTIONS,
    AIModel,
    get_models_by_modality,
)


class TestAIModelModalityValidation(unittest.TestCase):
    def test_validate_modalities_normalizes_and_deduplicates(self):
        doc = AIModel(modalities=" Text , Vision , Text, OCR ")
        doc._validate_modalities()
        self.assertEqual(doc.modalities, "Text,Vision,OCR")

    def test_validate_modalities_empty_passes(self):
        doc = AIModel(modalities="")
        doc._validate_modalities()
        self.assertEqual(getattr(doc, "modalities", ""), "")

    def test_validate_modalities_invalid_throws(self):
        doc = AIModel(modalities="Text, InvalidModality")
        with self.assertRaises(ThrowError) as cm:
            doc._validate_modalities()
        self.assertIn("Invalid modality value(s): InvalidModality", str(cm.exception))


class TestGetModelsByModality(unittest.TestCase):
    def setUp(self):
        frappe_mock.db.sql.reset_mock()

    def test_missing_modality_filter_throws(self):
        with self.assertRaises(ThrowError) as cm:
            get_models_by_modality("AI Model", "", "", 0, 20, {})
        self.assertIn("Missing required filter: modality", str(cm.exception))

    def test_invalid_modality_filter_throws(self):
        with self.assertRaises(ThrowError) as cm:
            get_models_by_modality("AI Model", "", "", 0, 20, {"modality": "Magic"})
        self.assertIn("Invalid modality: Magic", str(cm.exception))

    def test_query_includes_replace_spaces_find_in_set(self):
        frappe_mock.db.sql.return_value = [("GPT-4", "gpt-4o")]
        res = get_models_by_modality("AI Model", "gpt", "", 0, 20, {"modality": "Vision", "provider": "OpenAI"})

        self.assertEqual(res, [("GPT-4", "gpt-4o")])
        frappe_mock.db.sql.assert_called_once()
        sql, params = frappe_mock.db.sql.call_args[0]
        self.assertIn("REPLACE(IFNULL(modalities, ''), ' ', '')", sql)
        self.assertIn("provider = %(provider)s", sql)
        self.assertEqual(params["modality"], "Vision")
        self.assertEqual(params["provider"], "OpenAI")


if __name__ == "__main__":
    unittest.main()
