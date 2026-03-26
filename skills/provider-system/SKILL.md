---
name: provider-system
category: integrations
version: 1.0.0
---

# Provider & LiteLLM Integration

HUF uses LiteLLM as its unified provider layer, enabling seamless access to 100+ LLM providers through a single interface. This skill covers the provider architecture, model normalization, API key management, and extension points.

## Overview

The Provider System acts as a routing and abstraction layer between HUF agents and various AI providers. It enables:

- **Unified Access**: Single interface for OpenAI, Anthropic, Google, OpenRouter, xAI, Mistral, and 100+ more
- **Model Normalization**: Automatic conversion between user-friendly names (`gpt-4-turbo`) and LiteLLM format (`openai/gpt-4-turbo`)
- **Environment-based Auth**: Handles API keys via environment variables or direct parameters
- **Streaming Support**: Real-time streaming responses with SSE
- **Tool Calling**: Multi-turn tool execution across all supported providers
- **Error Handling**: Built-in retry logic, rate limit handling, and graceful fallbacks

## Key Files

| File | Purpose |
|------|---------|
| `huf/ai/run.py` | Central routing layer (`RunProvider` class) - routes all provider requests |
| `huf/ai/providers/litellm.py` | Unified LiteLLM implementation - handles 100+ providers |
| `huf/ai/providers/openrouter.py` | Dedicated OpenRouter provider with custom retry logic |
| `huf/ai/providers/openai.py` | Legacy OpenAI provider (kept for backward compatibility) |
| `huf/ai/providers/anthropic.py` | Legacy Anthropic provider (kept for backward compatibility) |
| `huf/ai/providers/google.py` | Legacy Google provider (kept for backward compatibility) |
| `huf/huf/doctype/ai_provider/ai_provider.py` | DocType for provider credential storage |
| `huf/huf/doctype/ai_provider/ai_provider.json` | DocType schema for AI Provider |
| `huf/huf/doctype/ai_model/ai_model.py` | DocType for model configuration |
| `huf/huf/doctype/ai_model/ai_model.json` | DocType schema for AI Model |
| `huf/ai/sdk_tools.py` | Tool creation and execution for agents |
| `huf/ai/tool_serializer.py` | Provider-agnostic tool serialization |

## How It Works

### 1. Provider Routing Flow

```
Agent Execution
      ↓
RunProvider.run()  [huf/ai/run.py]
      ↓
  ┌─────────────────┐
  │ Try LiteLLM     │ ← Default path for all providers
  └─────────────────┘
      ↓
  ┌─────────────────────────┐
  │ litellm.run()           │ [huf/ai/providers/litellm.py]
  │ - Normalize model name  │
  │ - Setup API key         │
  │ - Execute with retry    │
  └─────────────────────────┘
      ↓
  Return Result
```

### 2. Model Name Normalization

The system automatically normalizes model names to LiteLLM format:

| User Input | Normalized Output | Provider |
|------------|-------------------|----------|
| `gpt-4-turbo` | `openai/gpt-4-turbo` | OpenAI |
| `claude-3-opus` | `anthropic/claude-3-opus` | Anthropic |
| `gemini-pro` | `gemini/gemini-pro` | Google |
| `grok-4` | `xai/grok-4` | xAI |
| `mistral-large` | `mistral/mistral-large` | Mistral |

**Implementation**: `_normalize_model_name()` in `litellm.py`

```python
provider_prefix_map = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "gemini",
    "gemini": "gemini",      # Alias
    "grok": "xai",           # Alias for xAI
    "xai": "xai",
    "mistral": "mistral",
    "alibaba": "dashscope",
    "cohere": "cohere",
    "perplexity": "perplexity",
    "meta": "meta-llama",
}
```

If model already has provider prefix (e.g., `openai/gpt-4-turbo`), it's used as-is.

### 3. API Key Management

Different providers require different authentication methods:

**Environment Variable Providers** (set via `os.environ`):
- OpenRouter → `OPENROUTER_API_KEY`
- xAI/Grok → `XAI_API_KEY`
- DeepSeek → `DEEPSEEK_API_KEY`
- Mistral → `MISTRAL_API_KEY`
- Dashscope (Alibaba) → `DASHSCOPE_API_KEY`
- Google/Gemini → `GEMINI_API_KEY`
- Cohere → `COHERE_API_KEY`
- Perplexity → `PERPLEXITY_API_KEY`

**Direct API Key** (passed to LiteLLM):
- OpenAI
- Anthropic
- Most other providers

**Implementation**: `_setup_api_key()` in `litellm.py`

### 4. AI Provider DocType

Stores provider credentials securely using Frappe's Password field type.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `provider_name` | Data | Unique identifier (e.g., "OpenAI", "Anthropic") |
| `api_key` | Password | Encrypted API key |
| `slug` | Data | Optional slug for API routing |
| `chef` | Data | Provider standard name (internal) |
| `is_local_llm` | Check | Flag for local/self-hosted LLMs |
| `url` | Data | Base URL for local LLMs |
| `port` | Int | Port for local LLMs |

### 5. AI Model DocType

Defines available models and their capabilities.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `model_name` | Data | Model identifier (e.g., "gpt-4-turbo") |
| `provider` | Link | Link to AI Provider |
| `modalities` | Select | Supported tasks: Text, Image, Text-to-Speech, Transcription, Embeddings |

### 6. Multi-turn Tool Calling

The LiteLLM provider supports multiple rounds of tool calls in a single execution:

```python
MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10

for round_num in range(MAX_ROUNDS):
    # Call LLM with tools
    response = await litellm.completion(**kwargs)
    
    # If no tool calls, return result
    if not choice.tool_calls:
        return SimpleResult(choice.content)
    
    # Execute tool calls
    for tool_call in choice.tool_calls:
        result = await _execute_tool_call(tool, args, context)
        tool_results.append(result)
    
    # Add results to messages for next round
    messages.extend(tool_results)
```

### 7. Streaming Support

SSE streaming is supported via `run_stream()`:

```python
async for chunk in stream:
    delta = chunk.choices[0].delta
    
    if delta.content:
        yield {"type": "delta", "content": delta.content}
    
    if delta.tool_calls:
        # Buffer and execute tool calls
        ...
```

Endpoint: `/huf/stream/<agent_name>`

### 8. Parameter Handling

Temperature and other parameters are read from Agent DocType (priority 1), then `agent.model_settings` (priority 2), then defaults.

**Special Cases**:
- GPT-5 models only support `temperature=1` → handled via `litellm.drop_params = True`
- `response_format` (JSON mode) conflicts with tools on some providers → auto-detected and tools disabled

## Extension Points

### Adding a New LiteLLM-Compatible Provider

Most new providers work automatically with LiteLLM. To add support:

1. **Create AI Provider document** in Frappe Desk:
   - Provider Name: e.g., "Cohere"
   - API Key: Your API key

2. **Create AI Model document**:
   - Model Name: e.g., "command-r"
   - Provider: Link to the AI Provider

3. **If provider requires environment variable**, add to `_setup_api_key()`:

```python
env_var_providers = {
    # ... existing providers ...
    "newprovider": "NEWPROVIDER_API_KEY",
}
```

4. **If provider has custom prefix mapping**, add to `_normalize_model_name()`:

```python
provider_prefix_map = {
    # ... existing mappings ...
    "newprovider": "newprovider",
    "new_alias": "newprovider",  # Optional alias
}
```

### Creating a Custom Provider Module

For providers not supported by LiteLLM, create a custom module:

1. **Create file**: `huf/ai/providers/custom_provider.py`

2. **Implement `run()` function**:

```python
import frappe
from types import SimpleNamespace

class SimpleResult:
    def __init__(self, final_output, usage=None, new_items=None):
        self.final_output = final_output
        self.usage = usage or {}
        self.new_items = new_items or []

async def run(agent, enhanced_prompt, provider, model, context=None):
    """Custom provider implementation."""
    # Get API key from AI Provider
    provider_doc = frappe.get_doc("AI Provider", provider)
    api_key = provider_doc.get_password("api_key")
    
    # Implement your provider logic
    # ...
    
    return SimpleResult(
        final_output="Response from custom provider",
        usage={"input_tokens": 100, "output_tokens": 50}
    )
```

3. **The RunProvider will automatically discover** and use your module as fallback if LiteLLM fails.

### Adding TTS Support for Cross-Provider Audio

HUF supports cross-provider TTS (e.g., OpenAI agent + ElevenLabs TTS):

1. **Create separate AI Provider** for TTS service (e.g., "ElevenLabs")

2. **Create AI Model** for TTS (e.g., "eleven_multilingual_v2")

3. **Configure Agent**:
   - Set `tts_model` field to the TTS AI Model
   - Set `tts_voice` field (e.g., "21m00Tcm4TlvDq8ikWAM" for ElevenLabs)

4. **TTS Resolution** (in `huf/ai/sdk_tools.py`):
   - Priority 1: `model` param in tool call → uses main provider's key
   - Priority 2: `agent.tts_model` → uses TTS model's provider key
   - Priority 3: Fallback to main provider's default TTS

## Dependencies

```toml
# pyproject.toml
[project.dependencies]
"litellm>=1.0.0" = "*"
```

Install: `bench setup requirements` or `pip install litellm>=1.0.0`

## Gotchas

### 1. API Key Storage
API keys are stored using Frappe's Password field type, which encrypts values. Access via:
```python
api_key = provider_doc.get_password("api_key")  # Never access .api_key directly
```

### 2. OpenRouter Special Handling
OpenRouter requires `OPENROUTER_API_KEY` environment variable AND model names must include `openrouter/` prefix. The system handles this automatically via `_normalize_model_name()`.

### 3. Temperature Restrictions
Some models (like GPT-5) only support `temperature=1`. LiteLLM will error if other values are passed. HUF sets `litellm.drop_params = True` to silently drop unsupported params instead of erroring.

### 4. Tool + JSON Mode Conflict
Some providers don't support tools and `response_format` (JSON mode) simultaneously. The system auto-detects this conflict via error message keywords and retries without tools:

```python
conflict_keywords = [
    "response_format", "response mime type", 
    "tool", "function calling", "json", "unsupported"
]
```

### 5. Context Window Management
Messages are automatically trimmed to fit the model's context window using `litellm.utils.trim_messages`:

```python
messages = trim_messages(messages=messages, model=normalized_model)
```

### 6. Rate Limit Handling
The OpenRouter provider implements exponential backoff with jitter for 429 errors:

```python
delay = 1
for attempt in range(max_retries):
    try:
        response = requests.post(...)
    except HTTPError as e:
        if response.status_code == 429:
            await asyncio.sleep(delay + random.uniform(0, 0.5))
            delay *= 2
```

### 7. Provider Name Case Insensitivity
Provider names are case-insensitive in routing:
```python
provider_lower = provider.lower()
```

### 8. LiteLLM Import Error
If LiteLLM is not installed, the system provides a helpful error message:
```
LiteLLM package is required but not installed.
To install:
1. Run: bench setup requirements
2. Or manually: pip install litellm>=1.0.0
3. Then restart your site: bench restart
```

### 9. Agent Settings Priority
Temperature and top_p are read from Agent DocType fields first (most reliable), then from `agent.model_settings`, then defaults:

```python
if agent_doc:
    temperature = agent_doc.temperature  # Priority 1
    top_p = agent_doc.top_p

if temperature is None and agent.model_settings:
    temperature = agent.model_settings.temperature  # Priority 2

if temperature is None:
    temperature = 0.7  # Default
```

### 10. Local LLM Support
For self-hosted/local LLMs, check the "Is Local LLM" box in AI Provider and set URL/PORT fields. The system will route requests to your local endpoint.
