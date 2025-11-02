# LiteLLM Migration - Implementation Notes

## Overview

This branch implements unified LiteLLM provider support while maintaining 100% backward compatibility with existing AgentFlo configurations.

## Changes Made

### 1. Added LiteLLM Dependency
- **File**: `pyproject.toml`
- **Change**: Added `litellm>=1.0.0` to dependencies
- **Impact**: LiteLLM will be installed when app is installed/updated

### 2. Created Unified LiteLLM Provider
- **File**: `agentflo/ai/providers/litellm.py`
- **Purpose**: Single unified provider implementation for all LLM providers
- **Features**:
  - Automatic model name normalization (e.g., "gpt-4-turbo" → "openai/gpt-4-turbo")
  - Supports 100+ providers via LiteLLM
  - OpenAI-compatible tool format (works with existing `serialize_tools()`)
  - Built-in retry logic, cost tracking, error handling
  - Multi-turn tool calling loop (same pattern as existing providers)

### 3. Updated Provider Routing
- **File**: `agentflo/ai/run.py`
- **Change**: Routes existing providers (OpenAI, Anthropic, Google, OpenRouter) to LiteLLM
- **Backward Compatibility**: 
  - Existing provider names work as-is
  - Existing model names work as-is (auto-normalized)
  - Existing API keys work as-is
  - Existing tools work as-is

## Backward Compatibility

✅ **Zero Breaking Changes**

- **API Keys**: Stored and retrieved exactly the same way (`AI Provider` DocType)
- **Model Names**: Auto-normalized (e.g., "gpt-4-turbo" → "openai/gpt-4-turbo")
- **Tool Calling**: Uses existing `serialize_tools()` function
- **Tool Execution**: Uses existing `_find_tool()` and `_execute_tool_call()` functions
- **Result Format**: Returns `SimpleResult` with same structure

## Testing Checklist

Before merging, verify:

- [ ] Existing OpenAI agents work
- [ ] Existing Anthropic agents work
- [ ] Existing Google/Gemini agents work
- [ ] Existing OpenRouter agents work
- [ ] Tool calling works for all providers
- [ ] Token usage tracking works
- [ ] Error handling works correctly
- [ ] Multi-turn conversations work

## New Providers via DocType

Users can now add new providers without code changes:

1. Create `AI Provider` document:
   - Name: Provider identifier (e.g., "XAI", "Mistral")
   - API Key: Provider API key

2. Create `AI Model` document:
   - Model Name: Use LiteLLM format (e.g., "xai/grok-4", "mistral/mistral-large-latest")
   - Provider: Link to AI Provider

3. Use in Agent:
   - Select the new provider and model
   - Works immediately!

## Migration Path

### Phase 1: Current Implementation (This Branch)
- ✅ LiteLLM added as unified provider
- ✅ Existing providers routed to LiteLLM
- ✅ Backward compatibility maintained
- ✅ Old provider files kept for reference

### Phase 2: Testing & Validation
- Test all existing agents
- Verify tool calling works
- Check token usage tracking
- Validate error handling

### Phase 3: Cleanup (Future)
- After validation, old provider files can be removed
- No DocType changes needed
- No user migration needed

## Known Limitations

1. **Environment Variables**: Some providers (OpenRouter, xAI, Mistral, Dashscope) require environment variables. These are set per-request in the code.

2. **Synchronous LiteLLM**: LiteLLM's `completion()` is synchronous, so we wrap it in `asyncio.to_thread()` to avoid blocking.

3. **Cost Tracking**: LiteLLM provides cost data, but it's not yet integrated into Agent Run cost tracking. This can be added in a future update.

## Files Changed

- `pyproject.toml` - Added litellm dependency
- `agentflo/ai/providers/litellm.py` - New unified provider (287 lines)
- `agentflo/ai/run.py` - Updated routing logic

## Files Not Changed (Backward Compatibility)

- `agentflo/ai/providers/openai.py` - Kept for reference
- `agentflo/ai/providers/anthropic.py` - Kept for reference
- `agentflo/ai/providers/google.py` - Kept for reference
- `agentflo/ai/providers/openrouter.py` - Kept for reference
- All DocTypes - No changes needed
- All existing agent configurations - Work as-is

## Next Steps

1. Install dependencies: `bench setup requirements` or `pip install litellm`
2. Test with existing agents
3. Verify tool calling works
4. Check token usage tracking
5. Merge when validated

