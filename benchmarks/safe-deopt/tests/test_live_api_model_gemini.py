# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for the real, Gemini-backed ``LiveAPIModel`` implementation (Issue A,
PLAN_V3): the transcript->``contents`` translator, the Gemini response parser, and
token-count flow-through into ``ModelStep``.

IMPORTANT -- these tests mock the HTTP/SDK call boundary, never a real call
-------------------------------------------------------------------------------
Every test here injects a fake ``_Provider`` (or calls ``_parse_gemini_response`` directly)
with a HAND-CONSTRUCTED response dict matching Gemini's documented ``generateContent``
response shape (confirmed against current API docs: ``candidates[0].content.parts``,
``usageMetadata.{promptTokenCount,candidatesTokenCount,cachedContentTokenCount}``, top-level
``modelVersion``). None of this is a VCR-style recorded response from a real call -- per the
project's secret-handling rules, a real response could embed request/response artifacts and
must never be captured as a test fixture. The one real API call this task makes is a
separate, manual connectivity check outside the test suite.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SAFE_DEOPT_DIR))

from recovery_harness import (  # noqa: E402
    AtomicTool,
    LiveAPIModel,
    ModelStep,
    ToolCallRequest,
    _ProviderResponse,
    _atomic_tools_to_gemini_declarations,
    _json_schema_to_gemini_schema,
    _parse_gemini_response,
    _schema,
    SYSTEM_PROMPT,
)


class _FakeProvider:
    """Records every ``generate()`` call it receives and returns a scripted sequence of
    ``_ProviderResponse`` -- the seam LiveAPIModel talks to, never HTTP/SDK details.
    """

    def __init__(self, responses: list[_ProviderResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def generate(self, *, system_instruction, contents, tool_declarations):
        self.calls.append(
            {
                "system_instruction": system_instruction,
                "contents": contents,
                "tool_declarations": tool_declarations,
            }
        )
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# _json_schema_to_gemini_schema / _atomic_tools_to_gemini_declarations
# ---------------------------------------------------------------------------


class TestSchemaTranslation(unittest.TestCase):
    def test_empty_schema_becomes_object_with_no_properties(self):
        self.assertEqual(_json_schema_to_gemini_schema({}), {"type": "OBJECT", "properties": {}})

    def test_translates_types_to_gemini_uppercase_and_keeps_required(self):
        schema = _schema({"operation_key": "string", "amount": "number"}, required=["operation_key"])
        gemini = _json_schema_to_gemini_schema(schema)
        self.assertEqual(gemini["type"], "OBJECT")
        self.assertEqual(gemini["properties"]["operation_key"], {"type": "STRING"})
        self.assertEqual(gemini["properties"]["amount"], {"type": "NUMBER"})
        self.assertEqual(gemini["required"], ["operation_key"])

    def test_atomic_tools_to_declarations_only_includes_available_tools(self):
        tools = {
            "read_open_items": AtomicTool(name="read_open_items", fn=lambda: None, is_write=False, description="read", parameters=_schema({})),
            "submit_allocation": AtomicTool(
                name="submit_allocation",
                fn=lambda **kw: None,
                is_write=True,
                description="submit",
                parameters=_schema({"allocation": "string", "operation_key": "string"}),
            ),
        }
        declarations = _atomic_tools_to_gemini_declarations(tools, ["submit_allocation"])
        self.assertEqual(len(declarations), 1)
        self.assertEqual(declarations[0]["name"], "submit_allocation")
        self.assertEqual(declarations[0]["parameters"]["properties"]["operation_key"], {"type": "STRING"})

    def test_atomic_tools_to_declarations_skips_unknown_names(self):
        declarations = _atomic_tools_to_gemini_declarations({}, ["escalate"])
        self.assertEqual(declarations, [])


# ---------------------------------------------------------------------------
# _parse_gemini_response -- hand-constructed response shapes
# ---------------------------------------------------------------------------


class TestParseGeminiResponse(unittest.TestCase):
    def test_parses_a_function_call_response(self):
        payload = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"functionCall": {"name": "submit_allocation", "args": {"allocation": "ALLOC-1", "operation_key": "opB"}}}],
                    },
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {"promptTokenCount": 123, "candidatesTokenCount": 17, "totalTokenCount": 140},
            "modelVersion": "gemini-1.5-flash-002",
        }
        response = _parse_gemini_response(payload)
        self.assertEqual(response.function_call, {"name": "submit_allocation", "args": {"allocation": "ALLOC-1", "operation_key": "opB"}})
        self.assertIsNone(response.text)
        self.assertEqual(response.prompt_tokens, 123)
        self.assertEqual(response.completion_tokens, 17)
        self.assertEqual(response.cached_tokens, 0)
        self.assertEqual(response.model_version, "gemini-1.5-flash-002")

    def test_parses_a_final_text_response(self):
        payload = {
            "candidates": [{"content": {"role": "model", "parts": [{"text": "Escalating: cannot establish a safe continuation."}]}, "finishReason": "STOP", "index": 0}],
            "usageMetadata": {"promptTokenCount": 88, "candidatesTokenCount": 9},
            "modelVersion": "gemini-1.5-flash-002",
        }
        response = _parse_gemini_response(payload)
        self.assertIsNone(response.function_call)
        self.assertEqual(response.text, "Escalating: cannot establish a safe continuation.")
        self.assertEqual(response.prompt_tokens, 88)
        self.assertEqual(response.completion_tokens, 9)

    def test_parses_cached_content_token_count_when_present(self):
        payload = {
            "candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP", "index": 0}],
            "usageMetadata": {"promptTokenCount": 500, "candidatesTokenCount": 5, "cachedContentTokenCount": 400},
        }
        response = _parse_gemini_response(payload)
        self.assertEqual(response.cached_tokens, 400)
        self.assertIsNone(response.model_version, "no modelVersion key in this hand-built payload -- must not be fabricated")

    def test_missing_usage_metadata_yields_zero_tokens_not_a_crash(self):
        payload = {"candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP", "index": 0}]}
        response = _parse_gemini_response(payload)
        self.assertEqual(response.prompt_tokens, 0)
        self.assertEqual(response.completion_tokens, 0)

    def test_no_candidates_yields_no_text_and_no_function_call(self):
        payload = {"usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 0}}
        response = _parse_gemini_response(payload)
        self.assertIsNone(response.text)
        self.assertIsNone(response.function_call)


# ---------------------------------------------------------------------------
# LiveAPIModel.next_step -- transcript -> contents translation, end to end, via a fake
# provider (never a real HTTP call)
# ---------------------------------------------------------------------------


class TestLiveAPIModelNextStep(unittest.TestCase):
    def _tools(self):
        return {
            "submit_allocation": AtomicTool(
                name="submit_allocation",
                fn=lambda **kw: None,
                is_write=True,
                description="submit",
                parameters=_schema({"allocation": "string", "operation_key": "string"}),
            ),
            "escalate": AtomicTool(name="escalate", fn=lambda **kw: None, is_write=False, description="escalate", parameters=_schema({"reason": "string"})),
        }

    def test_first_call_translates_system_and_user_turns_and_returns_tool_call(self):
        provider = _FakeProvider(
            [
                _ProviderResponse(
                    function_call={"name": "submit_allocation", "args": {"allocation": "ALLOC-1", "operation_key": "opB"}},
                    prompt_tokens=200,
                    completion_tokens=12,
                    model_version="gemini-1.5-flash-002",
                )
            ]
        )
        model = LiveAPIModel(model_id="gemini-1.5-flash", tools=self._tools(), provider=provider)

        transcript = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": {"original_request": "Complete the task."}},
        ]
        step = model.next_step(transcript=transcript, available_tools=["submit_allocation", "escalate"])

        self.assertIsInstance(step, ModelStep)
        self.assertEqual(step.tool_call, ToolCallRequest("submit_allocation", {"allocation": "ALLOC-1", "operation_key": "opB"}))
        self.assertEqual(step.estimated_prompt_tokens, 200)
        self.assertEqual(step.estimated_completion_tokens, 12)
        self.assertEqual(model.last_model_version, "gemini-1.5-flash-002")

        # -- the request the fake provider actually received --
        call = provider.calls[0]
        self.assertEqual(call["system_instruction"], SYSTEM_PROMPT)
        self.assertEqual(len(call["contents"]), 1, "only the user turn goes into contents; system is passed as system_instruction")
        self.assertEqual(call["contents"][0]["role"], "user")
        self.assertIn("original_request", call["contents"][0]["parts"][0]["text"])
        tool_names = {d["name"] for d in call["tool_declarations"]}
        self.assertEqual(tool_names, {"submit_allocation", "escalate"})

    def test_second_call_includes_own_prior_function_call_and_the_tool_result_as_function_response(self):
        provider = _FakeProvider(
            [
                _ProviderResponse(function_call={"name": "submit_allocation", "args": {"allocation": "ALLOC-1", "operation_key": "opB"}}, prompt_tokens=200, completion_tokens=12),
                _ProviderResponse(text="Escalating.", prompt_tokens=230, completion_tokens=6),
            ]
        )
        model = LiveAPIModel(model_id="gemini-1.5-flash", tools=self._tools(), provider=provider)

        transcript = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": {"original_request": "Complete the task."}},
        ]
        first = model.next_step(transcript=transcript, available_tools=["submit_allocation", "escalate"])
        self.assertIsNotNone(first.tool_call)

        # Mirrors what run_recovery itself appends after dispatching the tool call: ONLY a
        # tool-result entry -- never an entry for the model's own prior function-call turn
        # (see LiveAPIModel's class docstring "Transcript bookkeeping" section for why this
        # matters).
        transcript.append({"role": "tool", "tool_name": "submit_allocation", "content": {"error": "duplicate_operation_key"}})

        second = model.next_step(transcript=transcript, available_tools=["escalate"])
        self.assertEqual(second.final_text, "Escalating.")
        self.assertEqual(second.estimated_prompt_tokens, 230)

        call = provider.calls[1]
        contents = call["contents"]
        # user turn, then the model's OWN prior functionCall (reconstructed internally,
        # since the shared transcript never carried it), then the tool's functionResponse.
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(contents[1]["role"], "model")
        self.assertIn("functionCall", contents[1]["parts"][0])
        self.assertEqual(contents[1]["parts"][0]["functionCall"]["name"], "submit_allocation")
        self.assertEqual(contents[2]["role"], "user")
        function_response = contents[2]["parts"][0]["functionResponse"]
        self.assertEqual(function_response["name"], "submit_allocation")
        self.assertEqual(function_response["response"], {"error": "duplicate_operation_key"})
        # Only escalate is available on this second call (the write tool was gated off after
        # its guard rejection) -- the declarations sent reflect exactly that.
        self.assertEqual({d["name"] for d in call["tool_declarations"]}, {"escalate"})

    def test_non_dict_tool_result_is_wrapped_before_being_sent_as_a_function_response(self):
        provider = _FakeProvider([_ProviderResponse(text="done")])
        model = LiveAPIModel(model_id="gemini-1.5-flash", tools=self._tools(), provider=provider)
        transcript = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": {"original_request": "go"}},
            {"role": "tool", "tool_name": "read_open_items", "content": [1, 2, 3]},
        ]
        model.next_step(transcript=transcript, available_tools=[])
        contents = provider.calls[0]["contents"]
        function_response_part = contents[1]["parts"][0]["functionResponse"]
        self.assertEqual(function_response_part["response"], {"result": [1, 2, 3]})

    def test_final_text_step_has_no_tool_call_and_records_no_model_version_when_absent(self):
        provider = _FakeProvider([_ProviderResponse(text="All done.", prompt_tokens=50, completion_tokens=4)])
        model = LiveAPIModel(model_id="gemini-1.5-flash", tools=self._tools(), provider=provider)
        transcript = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": {"original_request": "go"}}]
        step = model.next_step(transcript=transcript, available_tools=[])
        self.assertIsNone(step.tool_call)
        self.assertEqual(step.final_text, "All done.")
        self.assertIsNone(model.last_model_version)


if __name__ == "__main__":
    unittest.main()
