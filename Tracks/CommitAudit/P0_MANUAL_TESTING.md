# P0 Manual Testing Instructions

Run these checks against staging after each batch deploy, and again briefly in production immediately after promotion.

---

## Environment

- Site with HUF installed and at least one active Agent.
- Agent configured with a provider/model and **conversation data enabled**.
- Access to Error Log doctype and `logs/huf.log` (or configured log sink).

---

## Batch 1 — `fix/p0-bare-except`

### 1.1 Conversation data injection (happy path)

1. Open an Agent Chat for an agent with `enable_conversation_data = 1` and `inject_conversation_data = 1`.
2. Use a tool or prior turn to set a conversation variable (e.g., `set_conversation_data(name="session_id", value="abc123")`).
3. Send a new user message.
4. **Expected:** Agent receives the variable in its system prompt and can reference it. No warnings in `logs/huf.log` related to `conversation_data`.

### 1.2 Malformed conversation data (failure path)

1. In `Agent Conversation`, manually set `conversation_data` to `"not valid json {"` or `null` for an active conversation.
2. Send a new user message in that conversation.
3. **Expected:**
   - The agent run still completes.
   - A `frappe.logger("huf").warning` line appears in `logs/huf.log` with text `Skipped conversation_data memory snapshot for conversation ...`.
   - No Error Log entry is created for this condition.

### 1.3 Sanity — bare except count

```bash
rg -n "except:\s*$" huf/ai --type py
```

**Expected:** no output.

---

## Batch 2 — `fix/p0-swallow-commit-hazards`

### 2.1 Knowledge context failure (Category A)

1. Temporarily break the knowledge source used by an agent (e.g., delete its SQLite file or set an invalid source).
2. Ask the agent a question that would normally trigger RAG.
3. **Expected:**
   - Agent returns a response without RAG context.
   - Error Log contains an entry titled `Knowledge context build failed — agent run continuing without RAG context`.
   - The Agent Run document still reaches `Success` status.

### 2.2 Tool result fallback (Category A)

1. Create a custom tool that returns plain text (not valid JSON).
2. Run the agent and invoke the tool.
3. **Expected:**
   - The agent sees the raw text result and continues.
   - Error Log contains an entry titled `Tool result JSON parse failed — using raw output`.

### 2.3 HTTP node non-JSON response (Category A)

1. In a Flow, add an `http_request` node that calls a public endpoint returning plain text (e.g., `https://httpbin.org/base64/SGVsbG8=`).
2. Run the flow.
3. **Expected:**
   - Flow continues and `result.data` contains the text body.
   - Error Log contains an entry titled `HTTP response JSON parse failed — falling back to text`.

### 2.4 Image generation failure path (Category B)

1. Configure an agent with image generation support.
2. Temporarily lock or corrupt the `Agent Message` table so `MAX(conversation_index)` fails (in staging only).
3. Ask the agent to generate an image.
4. **Expected:**
   - The tool call returns `success: false` with a user-visible `Message Ordering Error`.
   - No new `Agent Message` row of kind `Image` is inserted at index `1`.
   - Error Log contains `Failed to compute conversation_index for <conversation_id>`.

### 2.5 Audio generation failure path (Category B)

Same as 2.4, but use the `generate_audio` tool. **Expected:** no `Agent Message` row of kind `Audio` is inserted at index `1`.

### 2.6 Image/audio happy path

1. Use the `generate_image` tool normally.
2. Use the `generate_audio` tool normally.
3. **Expected:** Messages of kind `Image` and `Audio` are created with sequential `conversation_index` values and display correctly in chat.

---

## Error Log watchlist (both batches)

After each deploy, monitor Error Log for 48–72 hours for any **new** error patterns other than the expected titles above. If unexpected volumes appear, revert the batch and investigate before re-promoting.

Expected new Error Log titles:

- `Knowledge context build failed — agent run continuing without RAG context`
- `Tool result JSON parse failed — using raw output`
- `HTTP response JSON parse failed — falling back to text`
- `Failed to compute conversation_index for <conversation_id>`

Expected `logs/huf.log` warnings:

- `Skipped conversation_data memory snapshot for conversation ...`
- `Skipped double-decoding of conversation_data state: ...`
