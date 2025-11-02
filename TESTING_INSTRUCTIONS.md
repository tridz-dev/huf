# Testing Instructions for LiteLLM Migration

## Prerequisites

1. **You're on the branch**: `feature/litellm-unified-migration`
2. **Site is using this branch**: Ensure your Frappe site has this branch checked out

## Step 1: Install LiteLLM Dependency

In your Frappe site directory:

```bash
# Option 1: Using bench (recommended)
bench setup requirements

# Option 2: Manual installation
pip install litellm>=1.0.0

# Option 3: If using uv (as per your user rules)
cd /path/to/your/site
uv pip install litellm>=1.0.0
```

## Step 2: Restart Your Site

After installing the dependency:

```bash
bench restart
```

## Step 3: Test Existing Agents

### Test 1: OpenAI Agent
1. Go to **Agent** list
2. Find an existing OpenAI agent (or create one)
3. Ensure it has:
   - Provider: OpenAI (existing AI Provider document)
   - Model: e.g., "gpt-4-turbo" or "gpt-3.5-turbo"
   - Tools assigned (optional, but recommended for full testing)
4. Run the agent via **Agent Console** or **Agent Chat**
5. **Expected**: Should work exactly as before

### Test 2: Anthropic Agent
1. Find/create an Anthropic agent
2. Ensure it has:
   - Provider: Anthropic
   - Model: e.g., "claude-3-opus-20240229" or "claude-3-sonnet-20240229"
3. Run the agent
4. **Expected**: Should work exactly as before

### Test 3: Google/Gemini Agent
1. Find/create a Google agent
2. Ensure it has:
   - Provider: Google
   - Model: e.g., "gemini-pro" or "gemini-pro-vision"
3. Run the agent
4. **Expected**: Should work exactly as before

### Test 4: OpenRouter Agent
1. Find/create an OpenRouter agent
2. Ensure it has:
   - Provider: OpenRouter
   - Model: e.g., "openai/gpt-4-turbo" or "anthropic/claude-3-opus"
3. Run the agent
4. **Expected**: Should work exactly as before

## Step 4: Test Tool Calling

1. Create or use an agent with tools assigned
2. Ask the agent to use a tool (e.g., "Get me the list of customers")
3. **Expected**:
   - Tool is called correctly
   - Tool results are returned
   - Agent Run shows tool calls in `Agent Tool Call` documents

## Step 5: Test Token Usage Tracking

1. Run any agent
2. Check the **Agent Run** document
3. **Expected**:
   - `input_tokens` is populated
   - `output_tokens` is populated
   - `total_tokens` is calculated

## Step 6: Test Error Handling

1. Test with invalid API key (temporarily)
2. **Expected**: Clear error message, Agent Run status = "Failed"

## Step 7: Test New Provider (Optional)

Try adding a new provider that wasn't supported before:

1. Create **AI Provider**:
   - Name: `XAI` (or `Mistral`, `Alibaba`, etc.)
   - API Key: Your provider API key

2. Create **AI Model**:
   - Model Name: `xai/grok-4` (use LiteLLM format with provider prefix)
   - Provider: Link to the XAI provider

3. Create **Agent**:
   - Provider: XAI
   - Model: xai/grok-4
   - Tools: Assign some tools

4. Run the agent
5. **Expected**: Should work immediately without code changes!

## Troubleshooting

### Issue: "LiteLLM not installed"
**Solution**: Run `pip install litellm>=1.0.0` or `bench setup requirements`

### Issue: "ImportError: cannot import name 'litellm'"
**Solution**: 
1. Verify litellm is installed: `pip list | grep litellm`
2. Restart bench: `bench restart`

### Issue: "API Error" or authentication errors
**Solution**:
1. Check API key is correctly configured in `AI Provider` document
2. For OpenRouter/xAI/Mistral: API key should be in the provider document
3. Check error logs: `bench --site [sitename] console` → `frappe.log_error(...)`

### Issue: Model not found
**Solution**:
- For existing providers: Model name should work as-is (auto-normalized)
- For new providers: Use LiteLLM format: `provider/model-name` (e.g., `xai/grok-4`)

### Issue: Tool calling not working
**Solution**:
1. Verify tools are assigned to the agent
2. Check tool descriptions are clear
3. Check Agent Run logs for tool call errors

## Verification Checklist

After testing, verify:

- [ ] OpenAI agents work
- [ ] Anthropic agents work  
- [ ] Google/Gemini agents work
- [ ] OpenRouter agents work
- [ ] Tool calling works
- [ ] Token usage is tracked
- [ ] Error handling works
- [ ] Multi-turn conversations work
- [ ] Existing configurations work without changes

## What to Report

If you find issues, please report:
1. Provider and model used
2. Error message (if any)
3. Agent Run document details
4. Relevant logs from error log

## Rollback (If Needed)

If you need to rollback:

```bash
# Switch back to develop branch
git checkout develop

# Restart site
bench restart
```

The old provider files are still in the codebase, so rolling back is safe.

