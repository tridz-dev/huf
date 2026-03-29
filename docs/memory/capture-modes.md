# Capture Modes

Capture modes control **when** and **how** memories are extracted from conversations. Choosing the right mode is crucial for balancing capture quality, system performance, and user experience.

## Capture Stages

### 1. In-Prompt (`in_prompt`)

**How it works**: Memory extraction happens during the main LLM call, within the same prompt.

```
User Message
     ↓
[Memory Extraction Instructions]
     ↓
[Main Task Instructions]
     ↓
LLM Response (includes memory + answer)
```

**Pros**:
- Fastest (single LLM call)
- Context is fresh
- No additional latency

**Cons**:
- Competes with main task for context window
- May reduce answer quality
- Limited extraction complexity

**Best For**:
- Simple, structured extractions
- High-frequency capture
- Resource-constrained environments

**Example Use Case**: A bot that needs to immediately note user preferences mentioned in conversation.

---

### 2. Post-Response Synchronous (`post_response_sync`)

**How it works**: Memory extraction happens immediately after the main response, blocking until complete.

```
User Message
     ↓
LLM Response (sent to user immediately)
     ↓
[Wait]
     ↓
Memory Extraction (same context)
     ↓
Memory Stored
```

**Pros**:
- Doesn't interfere with main response
- Full context available
- Immediate capture

**Cons**:
- Adds latency to response time
- User waits for capture to complete
- Resource intensive

**Best For**:
- Critical memories that must be captured
- Low-frequency capture (e.g., end of conversation)
- When immediate consistency is required

**Example Use Case**: A support bot capturing issue details before the conversation continues.

---

### 3. Post-Response Asynchronous (`post_response_async`) ⭐ Recommended

**How it works**: Memory extraction happens in the background after the response is sent.

```
User Message
     ↓
LLM Response (sent to user immediately)
     ↓
[Background Process]
     ↓
Memory Extraction (queued)
     ↓
Memory Stored (user not waiting)
```

**Pros**:
- No user-perceived latency
- Can use more complex extraction
- Scales well

**Cons**:
- Slight delay before memory is available
- Requires background job infrastructure
- Potential for race conditions

**Best For**:
- Most production use cases
- Complex extraction logic
- High-throughput systems

**Example Use Case**: A general assistant that captures conversation summaries without slowing down responses.

---

### 4. Conversation End (`conversation_end`)

**How it works**: Memories are captured when the conversation is explicitly or implicitly ended.

```
Conversation Proceeds...
     ↓
[Multiple Turns]
     ↓
Conversation Ends (manual/timeout/heuristic)
     ↓
Batch Memory Extraction
     ↓
Memories Stored
```

**Pros**:
- Complete conversation context available
- Batch processing efficient
- Natural summary point

**Cons**:
- Memories not available during conversation
- May miss time-sensitive information
- Requires conversation boundary detection

**Best For**:
- Summarization
- Retrospective analysis
- Non-real-time memory needs

**Example Use Case**: A meeting assistant that summarizes the entire discussion after the meeting ends.

---

### 5. Scheduled (`scheduled`)

**How it works**: Memories are captured at specific times or intervals, independent of conversations.

```
Scheduled Time Arrives
     ↓
Collect Relevant Conversations
     ↓
Batch Processing
     ↓
Memories Stored
```

**Pros**:
- Predictable resource usage
- Can process large batches
- No impact on real-time performance

**Cons**:
- Delayed capture
- May miss context
- Requires scheduling infrastructure

**Best For**:
- Nightly batch processing
- Report generation
- Maintenance tasks

**Example Use Case**: A daily summary of all customer interactions for a support team.

## Capture Frequency

Frequency determines **how often** capture is attempted within a conversation.

### Every Run

**Behavior**: Attempt capture on every agent execution.

**Use When**:
- Every interaction is significant
- Using rules-only capture (fast)
- Storage is not a concern

**Caution**: Can generate many duplicate or low-value memories.

### Every N Runs

**Behavior**: Capture every Nth execution.

**Use When**:
- Regular but not continuous capture needed
- Balancing coverage with overhead
- Monitoring long-running processes

**Example**: Capture every 5th message to get periodic snapshots.

### Every N Turns

**Behavior**: Capture after every N message turns.

**Use When**:
- Conversation-based capture preferred
- Capturing at natural breakpoints
- Batch processing by turns

**Example**: Capture summary every 10 turns.

### Conversation End

**Behavior**: Capture only when conversation ends.

**Use When**:
- Summarization is the goal
- Complete context is important
- Real-time availability not needed

### Manual

**Behavior**: Only capture when explicitly triggered.

**Use When**:
- User controls memory creation
- Specific capture points known
- Minimizing automatic capture

### Scheduled

**Behavior**: Capture at specific times.

**Use When**:
- Batch processing preferred
- Off-peak processing desired
- Analyzing conversation patterns

## Conversation End Detection

When using `conversation_end` frequency, you need to detect when a conversation ends:

### Manual Close

**Trigger**: User explicitly ends the conversation.

**Implementation**:
- User clicks "End Chat"
- API call to close conversation
- Explicit signal in conversation

**Pros**: Accurate, user-controlled
**Cons**: Users may forget

### Idle Timeout

**Trigger**: No activity for N minutes.

**Configuration**:
```python
conversation_end_strategy = "idle_timeout"
idle_timeout_minutes = 30
```

**Pros**: Automatic, handles abandoned conversations
**Cons**: May trigger prematurely or too late

**Best Practices**:
- 15-30 minutes for chat
- 5-10 minutes for quick interactions
- 60+ minutes for deep work sessions

### Heuristic Detection

**Trigger**: AI detects conversation completion.

**Signals**:
- User says goodbye/thank you
- Task completion indicated
- Natural conclusion reached
- No follow-up questions

**Pros**: Smart, context-aware
**Cons**: May miss edge cases

**Example Prompt for Heuristic**:
```
Analyze this conversation. Has it naturally concluded?
Consider: goodbyes, task completion, no open questions.
Return: {"should_end": true/false, "reason": "..."}
```

### Never

**Trigger**: Manual only.

**Use Case**: Testing, explicit capture workflows.

## Producer Modes

Producer modes control **who** extracts the memory.

### Main Agent

**How it works**: The agent itself extracts memories while generating responses.

**Pros**:
- No additional LLM calls
- Agent knows its own context
- Fast

**Cons**:
- Divided attention
- May miss important details
- Biased by current task

**Best For**: Simple extractions by capable agents.

### Memory Agent (Dedicated)

**How it works**: A separate agent specialized in memory extraction.

**Configuration**:
```python
capture_owner = "memory_agent"
memory_agent = "MemoryExtractor"  # Name of dedicated agent
```

**Pros**:
- Specialized for extraction
- Doesn't distract main agent
- Can be fine-tuned

**Cons**:
- Additional configuration
- Extra LLM call
- More complex

**Best For**: High-quality extraction needs.

### Post-Run LLM

**How it works**: A fresh LLM call for extraction after the main response.

**Pros**:
- Clean slate for extraction
- Can use different model
- Focused task

**Cons**:
- Additional latency
- Extra cost
- Context may be stale

**Best For**: Complex extraction, different model for capture vs response.

### Rules-Only

**How it works**: Pattern matching and rules, no LLM involved.

**Pros**:
- Fastest (no LLM)
- Deterministic
- Cheap

**Cons**:
- Limited flexibility
- Requires predefined patterns
- May miss nuance

**Best For**: Structured data, known patterns, performance-critical.

**Example Rules**:
```python
# Extract email addresses
if "@" in text and "." in text.split("@")[-1]:
    extract_as("contact_email")

# Extract phone numbers
if matches_pattern(r"\d{3}-\d{3}-\d{4}", text):
    extract_as("phone_number")
```

## Combining Modes

You can combine modes for sophisticated capture strategies:

### Strategy 1: Real-time + Summary

```python
# Quick rule-based capture during conversation
capture_owner = "rules_only"
capture_stage = "in_prompt"
capture_frequency_type = "every_n_turns"
capture_frequency_value = 3

# Plus async extraction at end
additional_capture = {
    "stage": "conversation_end",
    "owner": "post_run_llm",
    "frequency": "conversation_end"
}
```

### Strategy 2: Conservative + Aggressive Fallback

```python
# Primary: conservative, high quality
primary_policy = {
    "min_confidence": 0.8,
    "capture_owner": "post_run_llm",
    "require_json_schema_match": True
}

# Fallback: capture more if primary misses
fallback_policy = {
    "min_confidence": 0.5,
    "capture_owner": "main_agent",
    "allow_open_schema": True
}
```

## Performance Considerations

| Mode | Latency | Cost | Quality | Complexity |
|------|---------|------|---------|------------|
| in_prompt | Low | Low | Medium | Low |
| post_response_sync | High | Medium | High | Low |
| post_response_async | None | Medium | High | Medium |
| conversation_end | None | Low | High | Medium |
| scheduled | None | Low | High | High |

## Decision Matrix

Choose your capture configuration based on:

| Requirement | Recommended Configuration |
|-------------|---------------------------|
| Minimal latency | `in_prompt` + `rules_only` |
| Maximum quality | `post_response_async` + `post_run_llm` |
| Complete summaries | `conversation_end` + `post_run_llm` |
| Production safety | `post_response_async` + `memory_agent` |
| High throughput | `every_n_turns` + `rules_only` |
| User privacy | `manual` + user confirmation |

## Next Steps

- Learn about [Retrieval](./retrieval.md) to understand how memories are used
- Review [Best Practices](./best-practices.md) for production tips
- See the [API Reference](./api-reference.md) for programmatic control