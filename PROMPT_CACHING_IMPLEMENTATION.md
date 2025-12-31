# Prompt Caching Implementation

This document describes the implementation of LiteLLM prompt caching support in Huf.

## Overview

Prompt caching allows agents to cache repeated prompt content, reducing token costs for subsequent requests. This feature is supported by OpenAI, Anthropic, Bedrock, and Deepseek providers via LiteLLM.

## Changes Made

### 1. Agent DocType (`huf/huf/doctype/agent/agent.json`)

Added new fields for prompt caching configuration:
- **`enable_prompt_caching`** (Check): Enable/disable prompt caching for this agent
- **`cache_control_type`** (Select): Cache control type - "ephemeral" for Anthropic, "auto" for OpenAI/Deepseek
- **`cache_system_message`** (Check): Whether to cache the system message/instructions
- **`cache_conversation_history`** (Check): Whether to cache conversation history messages

These fields are located in a new "Prompt Caching" section under the LLM Configuration tab.

### 2. Agent Run DocType (`huf/huf/doctype/agent_run/agent_run.json`)

Added field to track cached tokens:
- **`cached_tokens`** (Int): Number of cached tokens that were reused from prompt cache

### 3. LiteLLM Provider (`huf/ai/providers/litellm.py`)

Updated both `run()` and `run_stream()` functions to:
- Check if prompt caching is enabled for the agent
- Validate model support using `supports_prompt_caching()` from LiteLLM
- Format messages with `cache_control` based on provider:
  - **Anthropic**: Uses content array format with `cache_control: {"type": "ephemeral"}`
  - **OpenAI/Deepseek**: Uses content array format (LiteLLM handles cache_control automatically)
- Track `cached_tokens` from `usage.prompt_tokens_details.cached_tokens`
- Update cost calculation (LiteLLM's `completion_cost()` handles cached tokens automatically)

### 4. Agent Integration (`huf/ai/agent_integration.py`)

Updated token usage tracking to:
- Extract `cached_tokens` from usage response
- Store `cached_tokens` in Agent Run document

### 5. Agent Validation (`huf/huf/doctype/agent/agent.py`)

Added validation to:
- Check if model supports prompt caching when caching is enabled
- Show warning if model doesn't support caching
- Validate model is selected before enabling caching

## Usage

### Enabling Prompt Caching

1. Open an Agent document
2. Navigate to the "General" tab
3. Scroll to the "Prompt Caching" section
4. Enable "Enable Prompt Caching"
5. Select cache control type:
   - **ephemeral**: For Anthropic (charges for cache writes)
   - **auto**: For OpenAI/Deepseek (automatic caching)
6. Configure what to cache:
   - **Cache System Message**: Caches the agent's instructions
   - **Cache Conversation History**: Caches conversation history messages

### Supported Providers

- **OpenAI** (`openai/`): Automatic caching (requires prompts ≥1024 tokens)
- **Anthropic** (`anthropic/`): Ephemeral caching (charges for cache writes)
- **Bedrock** (`bedrock/`): Supported via AWS Bedrock
- **Deepseek** (`deepseek/`): Automatic caching

### Cost Calculation

Cached tokens are automatically accounted for in cost calculations via LiteLLM's `completion_cost()` function, which handles different pricing for cache-hit vs cache-miss tokens.

### Token Tracking

The `cached_tokens` field in Agent Run shows how many tokens were served from cache, helping users understand cost savings.

## Technical Details

### Message Format

For **Anthropic**:
```python
{
    "role": "system",
    "content": [
        {
            "type": "text",
            "text": "System instructions...",
            "cache_control": {"type": "ephemeral"}
        }
    ]
}
```

For **OpenAI/Deepseek**:
```python
{
    "role": "system",
    "content": [
        {
            "type": "text",
            "text": "System instructions..."
        }
    ]
}
```

LiteLLM automatically handles cache_control for OpenAI/Deepseek when content is in array format.

### Usage Response Format

LiteLLM returns usage information in this format:
```python
{
    "prompt_tokens": 2006,
    "completion_tokens": 300,
    "total_tokens": 2306,
    "prompt_tokens_details": {
        "cached_tokens": 1920
    }
}
```

## Limitations

1. **OpenAI**: Requires prompts with at least 1024 tokens for caching to be effective
2. **Anthropic**: Charges for cache writes (`cache_creation_input_tokens`)
3. **Conversation History**: Currently, conversation history is included in the enhanced prompt as text. To cache individual history messages separately, a refactor of message building would be needed.

## Future Enhancements

1. Auto-inject prompt caching for system messages automatically
2. Cache individual conversation history messages separately
3. Add UI indicators showing cache hit rates
4. Add analytics for cache effectiveness and cost savings

## Testing

To test prompt caching:

1. Create an agent with a long system message (≥1024 tokens for OpenAI)
2. Enable prompt caching
3. Run the agent multiple times with similar prompts
4. Check the `cached_tokens` field in Agent Run documents
5. Verify cost reduction in subsequent runs

## References

- [LiteLLM Prompt Caching Documentation](https://docs.litellm.ai/docs/completion/prompt_caching)
- [OpenAI Prompt Caching](https://platform.openai.com/docs/guides/prompt-caching)
- [Anthropic Prompt Caching](https://docs.anthropic.com/claude/docs/prompt-caching)
