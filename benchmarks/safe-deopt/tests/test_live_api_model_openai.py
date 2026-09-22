# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for the real, OpenAI-backed ``LiveAPIModel`` implementation (second model
family, Track-Item: v4-second-model-family): the ``AtomicTool`` -> OpenAI ``tools`` schema
translator, the OpenAI ``chat/completions`` response parser, and token-count flow-through
into ``ModelStep`` via the ``wire_format`` dispatch in ``LiveAPIModel.next_step``.

IMPORTANT -- these tests mock the HTTP call boundary, never a real call
-------------------------------------------------------------------------------
Every test here injects a fake ``_Provider`` (or calls ``_parse_openai_response`` directly)
with a HAND-CONSTRUCTED response dict matching OpenAI's documented ``chat/completions``
response shape (``choices[0].message.{content,tool_calls}``,
``usage.{prompt_tokens,completion_tokens,prompt_tokens_details.cached_tokens}``, top-level
``model``). None of this is a recorded response from a real call -- per the project's
secret-handling rules, a real response could embed request/response artifacts and must
never be captured as a test fixture. The one real API call this task makes is a separate,
manual smoke-test call outside the test suite.
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
    _atomic_tools_to_openai_declarations,
    _json_schema_to_openai_schema,
    _parse_openai_response,
    _schema,
    SYSTEM_PROMPT,
)


class _FakeOpenAIProvider:
    """Records every ``generate()`` call it receives and returns a scripted sequence of
    ``_ProviderResponse`` -- the seam ``LiveAPIModel`` talks to, never HTTP details. Sets
    ``wire_format = "openai"`` so ``LiveAPIModel`` builds OpenAI-native ``messages``/``tools``
    instead of Gemini-native ``contents``/``functionDeclarations``.
    """

    wire_format = "openai"

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
# _json_schema_to_openai_schema / _atomic_tools_to_openai_declarations
# ---------------------------------------------------------------------------


class TestSchemaTranslation(unittest.TestCase):
    def test_empty_schema_becomes_object_with_no_properties(self):
        self.assertEqual(_json_schema_to_openai_schema({}), {"type": "object", "properties": {}})

    def test_translates_types_keeping_lowercase_and_required(self):
        schema = _schema({"operation_key": "string", "amount": "number"}, required=["operation_key"])
        openai_schema = _json_schema_to_openai_schema(schema)
        self.assertEqual(openai_schema["type"], "object")
        self.assertEqual(openai_schema["properties"]["operation_key"], {"type": "string"})
        self.assertEqual(openai_schema["properties"]["amount"], {"type": "number"})
        self.assertEqual(openai_schema["required"], ["operation_key"])

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
        declarations = _atomic_tools_to_openai_declarations(tools, ["submit_allocation"])
        self.assertEqual(len(declarations), 1)
        decl = declarations[0]
        self.assertEqual(decl["type"], "function")
        self.assertEqual(decl["function"]["name"], "submit_allocation")
        self.assertEqual(decl["function"]["parameters"]["properties"]["operation_key"], {"type": "string"})

    def test_atomic_tools_to_declarations_skips_unknown_names(self):
        declarations = _atomic_tools_to_openai_declarations({}, ["escalate"])
        self.assertEqual(declarations, [])


# ---------------------------------------------------------------------------
# _parse_openai_response -- hand-constructed response shapes
# ---------------------------------------------------------------------------


class TestParseOpenAIResponse(unittest.TestCase):
    def test_parses_a_tool_call_response(self):
        payload = {
            "id": "chatcmpl-1",
            "model": "gpt-4o-mini-2024-07-18",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc123",
                                "type": "function",
                                "function": {"name": "submit_allocation", "arguments": '{"allocation": "ALLOC-1", "operation_key": "opB"}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                    "index": 0,
                }
            ],
            "usage": {"prompt_tokens": 123, "completion_tokens": 17, "total_tokens": 140},
        }
        response = _parse_openai_response(payload)
        self.assertEqual(
            response.function_call,
            {"name": "submit_allocation", "args": {"allocation": "ALLOC-1", "operation_key": "opB"}, "id": "call_abc123"},
        )
        self.assertIsNone(response.text)
        self.assertEqual(response.prompt_tokens, 123)
        self.assertEqual(response.completion_tokens, 17)
        self.assertEqual(response.cached_tokens, 0)
        self.assertEqual(response.model_version, "gpt-4o-mini-2024-07-18")

    def test_parses_a_final_text_response(self):
        payload = {
            "model": "gpt-4o-mini-2024-07-18",
            "choices": [{"message": {"role": "assistant", "content": "Escalating: cannot establish a safe continuation."}, "finish_reason": "stop", "index": 0}],
            "usage": {"prompt_tokens": 88, "completion_tokens": 9},
        }
        response = _parse_openai_response(payload)
        self.assertIsNone(response.function_call)
        self.assertEqual(response.text, "Escalating: cannot establish a safe continuation.")
        self.assertEqual(response.prompt_tokens, 88)
        self.assertEqual(response.completion_tokens, 9)

    def test_parses_cached_prompt_token_count_when_present(self):
        payload = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop", "index": 0}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 400}},
        }
        response = _parse_openai_response(payload)
        self.assertEqual(response.cached_tokens, 400)
        self.assertIsNone(response.model_version, "no 'model' key in this hand-built payload -- must not be fabricated")

    def test_missing_usage_yields_zero_tokens_not_a_crash(self):
        payload = {"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop", "index": 0}]}
        response = _parse_openai_response(payload)
        self.assertEqual(response.prompt_tokens, 0)
        self.assertEqual(response.completion_tokens, 0)

    def test_no_choices_yields_no_text_and_no_function_call(self):
        payload = {"usage": {"prompt_tokens": 10, "completion_tokens": 0}}
        response = _parse_openai_response(payload)
        self.assertIsNone(response.text)
        self.assertIsNone(response.function_call)

    def test_malformed_arguments_json_becomes_empty_args_not_a_crash(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{"id": "call_x", "type": "function", "function": {"name": "escalate", "arguments": "{not json"}}],
                    },
                    "finish_reason": "tool_calls",
                    "index": 0,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }
        response = _parse_openai_response(payload)
        self.assertEqual(response.function_call["name"], "escalate")
        self.assertEqual(response.function_call["args"], {})


# ---------------------------------------------------------------------------
# LiveAPIModel.next_step -- transcript -> OpenAI messages translation, end to end, via a
# fake provider (never a real HTTP call)
# ---------------------------------------------------------------------------


class TestLiveAPIModelNextStepOpenAI(unittest.TestCase):
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
        provider = _FakeOpenAIProvider(
            [
                _ProviderResponse(
                    function_call={"name": "submit_allocation", "args": {"allocation": "ALLOC-1", "operation_key": "opB"}, "id": "call_1"},
                    prompt_tokens=200,
                    completion_tokens=12,
                    model_version="gpt-4o-mini-2024-07-18",
                )
            ]
        )
        model = LiveAPIModel(model_id="gpt-4o-mini", tools=self._tools(), provider=provider)

        transcript = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": {"original_request": "Complete the task."}},
        ]
        step = model.next_step(transcript=transcript, available_tools=["submit_allocation", "escalate"])

        self.assertIsInstance(step, ModelStep)
        self.assertEqual(step.tool_call, ToolCallRequest("submit_allocation", {"allocation": "ALLOC-1", "operation_key": "opB"}))
        self.assertEqual(step.estimated_prompt_tokens, 200)
        self.assertEqual(step.estimated_completion_tokens, 12)
        self.assertEqual(model.last_model_version, "gpt-4o-mini-2024-07-18")

        call = provider.calls[0]
        self.assertEqual(call["system_instruction"], SYSTEM_PROMPT)
        self.assertEqual(len(call["contents"]), 1, "only the user turn goes into contents; system is passed as system_instruction")
        self.assertEqual(call["contents"][0]["role"], "user")
        self.assertIn("original_request", call["contents"][0]["content"])
        tool_names = {d["function"]["name"] for d in call["tool_declarations"]}
        self.assertEqual(tool_names, {"submit_allocation", "escalate"})
        for d in call["tool_declarations"]:
            self.assertEqual(d["type"], "function")

    def test_second_call_includes_own_prior_tool_call_and_the_tool_result_with_matching_id(self):
        provider = _FakeOpenAIProvider(
            [
                _ProviderResponse(function_call={"name": "submit_allocation", "args": {"allocation": "ALLOC-1", "operation_key": "opB"}, "id": "call_xyz"}, prompt_tokens=200, completion_tokens=12),
                _ProviderResponse(text="Escalating.", prompt_tokens=230, completion_tokens=6),
            ]
        )
        model = LiveAPIModel(model_id="gpt-4o-mini", tools=self._tools(), provider=provider)

        transcript = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": {"original_request": "Complete the task."}},
        ]
        first = model.next_step(transcript=transcript, available_tools=["submit_allocation", "escalate"])
        self.assertIsNotNone(first.tool_call)

        # Mirrors what run_recovery itself appends after dispatching the tool call: ONLY a
        # tool-result entry -- never an entry for the model's own prior tool-call turn.
        transcript.append({"role": "tool", "tool_name": "submit_allocation", "content": {"error": "duplicate_operation_key"}})

        second = model.next_step(transcript=transcript, available_tools=["escalate"])
        self.assertEqual(second.final_text, "Escalating.")
        self.assertEqual(second.estimated_prompt_tokens, 230)

        call = provider.calls[1]
        messages = call["contents"]
        # user turn, then the model's OWN prior assistant tool_calls turn (reconstructed
        # internally, since the shared transcript never carried it), then the tool result
        # message carrying the SAME tool_call_id the assistant turn declared.
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["tool_calls"][0]["id"], "call_xyz")
        self.assertEqual(messages[1]["tool_calls"][0]["function"]["name"], "submit_allocation")
        self.assertEqual(messages[2]["role"], "tool")
        self.assertEqual(messages[2]["tool_call_id"], "call_xyz")
        self.assertIn("duplicate_operation_key", messages[2]["content"])
        # Only escalate is available on this second call (the write tool was gated off after
        # its guard rejection) -- the declarations sent reflect exactly that.
        self.assertEqual({d["function"]["name"] for d in call["tool_declarations"]}, {"escalate"})

    def test_non_dict_tool_result_is_wrapped_before_being_sent_as_a_tool_message(self):
        provider = _FakeOpenAIProvider([_ProviderResponse(text="done")])
        model = LiveAPIModel(model_id="gpt-4o-mini", tools=self._tools(), provider=provider)
        transcript = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": {"original_request": "go"}},
            {"role": "tool", "tool_name": "read_open_items", "content": [1, 2, 3]},
        ]
        model.next_step(transcript=transcript, available_tools=[])
        messages = provider.calls[0]["contents"]
        self.assertEqual(messages[1]["role"], "tool")
        self.assertIn("[1, 2, 3]", messages[1]["content"])

    def test_final_text_step_has_no_tool_call_and_records_no_model_version_when_absent(self):
        provider = _FakeOpenAIProvider([_ProviderResponse(text="All done.", prompt_tokens=50, completion_tokens=4)])
        model = LiveAPIModel(model_id="gpt-4o-mini", tools=self._tools(), provider=provider)
        transcript = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": {"original_request": "go"}}]
        step = model.next_step(transcript=transcript, available_tools=[])
        self.assertIsNone(step.tool_call)
        self.assertEqual(step.final_text, "All done.")
        self.assertIsNone(model.last_model_version)


# ---------------------------------------------------------------------------
# _make_provider routing (gpt- prefix -> OpenAIHTTPProvider), without ever making a real
# HTTP call
# ---------------------------------------------------------------------------


class TestMakeProviderRoutesOpenAI(unittest.TestCase):
    def test_gpt_prefixed_model_id_routes_to_openai_provider_and_needs_a_key(self):
        import os

        from recovery_harness import _make_provider, OpenAIHTTPProvider

        saved = {var: os.environ.pop(var, None) for var in ("OPENAI_API_KEY", "OPENAI_KEY")}
        try:
            with self.assertRaises(RuntimeError):
                _make_provider("gpt-4o-mini")
            provider = _make_provider("gpt-4o-mini") if False else None  # never construct without a key
        finally:
            for var, value in saved.items():
                if value is not None:
                    os.environ[var] = value

        provider = OpenAIHTTPProvider(model_id="gpt-4o-mini", api_key="sk-not-a-real-key-for-testing")
        self.assertEqual(provider.wire_format, "openai")
        self.assertEqual(provider.model_id, "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
