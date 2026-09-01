# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for the generated huf.ai.model_catalogue module (see
scripts/gen_model_catalogue.py). Pure-Python data assertions -- no frappe
site context required, since huf/ai/model_catalogue.py itself imports
nothing from frappe.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_model_catalogue
Or standalone: python -m unittest huf.ai.tests.test_model_catalogue
"""

import unittest

from huf.ai.model_catalogue import DEPRECATED, MODELS

# Must match the "modalities" field's `options` in
# huf/huf/doctype/ai_model/ai_model.json exactly.
ALLOWED_MODALITIES = {
    "Text",
    "Image",
    "Text-to-Speech",
    "Transcription",
    "Embeddings",
    "Vision",
    "OCR",
    "Speech-to-Speech",
    "Video",
}


class TestModelCatalogue(unittest.TestCase):
    def test_models_is_non_empty(self):
        self.assertTrue(len(MODELS) > 0)

    def test_every_entry_has_model_name_and_provider(self):
        for entry in MODELS:
            self.assertIn("model_name", entry)
            self.assertIn("provider", entry)
            self.assertTrue(entry["model_name"])
            self.assertTrue(entry["provider"])
            self.assertIsInstance(entry["model_name"], str)
            self.assertIsInstance(entry["provider"], str)

    def test_no_duplicate_model_names(self):
        names = [entry["model_name"] for entry in MODELS]
        self.assertEqual(
            len(names), len(set(names)),
            "duplicate model_name values found in MODELS",
        )

    def test_modalities_values_are_from_allowed_set(self):
        for entry in MODELS:
            modalities = entry.get("modalities")
            if not modalities:
                continue
            for value in modalities.split(","):
                self.assertIn(
                    value, ALLOWED_MODALITIES,
                    f"{entry['model_name']!r} has modality {value!r} not in "
                    "the AI Model doctype's allowed set",
                )

    def test_context_window_is_positive_int_when_present(self):
        for entry in MODELS:
            if "context_window" not in entry:
                continue
            value = entry["context_window"]
            self.assertIsInstance(value, int)
            self.assertNotIsInstance(value, bool)
            self.assertGreater(value, 0)

    def test_max_output_tokens_is_positive_int_when_present(self):
        for entry in MODELS:
            if "max_output_tokens" not in entry:
                continue
            value = entry["max_output_tokens"]
            self.assertIsInstance(value, int)
            self.assertNotIsInstance(value, bool)
            self.assertGreater(value, 0)

    def test_models_sorted_deterministically(self):
        expected = sorted(MODELS, key=lambda m: (m["provider"], m["model_name"]))
        self.assertEqual(
            MODELS, expected,
            "MODELS is not sorted deterministically by (provider, model_name)",
        )

    def test_deprecated_names_not_present_in_models(self):
        model_names = {entry["model_name"] for entry in MODELS}
        overlap = set(DEPRECATED) & model_names
        self.assertEqual(
            overlap, set(),
            f"DEPRECATED names also present in MODELS: {overlap}",
        )

    def test_deprecated_is_a_tuple_of_strings(self):
        self.assertIsInstance(DEPRECATED, tuple)
        for name in DEPRECATED:
            self.assertIsInstance(name, str)
            self.assertTrue(name)


if __name__ == "__main__":
    unittest.main()
