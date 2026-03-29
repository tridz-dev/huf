# Getting Started with HUF Memory

This guide will walk you through setting up memory for your first agent.

## Prerequisites

- HUF installed and running
- At least one AI Provider configured
- Basic understanding of Frappe/ERPNext navigation

## Quick Start (5 minutes)

### Step 1: Verify Memory System is Installed

After installation, the Memory System automatically seeds default profiles and policies. Verify this:

1. Go to **HUF > Memory > Memory Profile**
2. You should see 7 system profiles:
   - Programming
   - General Knowledge
   - Travel Planning
   - Documentation
   - Science/Research
   - Language Learning
   - CRM

3. Go to **HUF > Memory > Memory Policy**
4. You should see 3 default policies:
   - Default Conservative
   - Default Aggressive
   - Default Rules-Only

### Step 2: Enable Memory on an Agent

1. Navigate to **HUF > Agent > Agent**
2. Select or create an agent
3. In the **Memory** section, check **Enable Memory**
4. Configure basic settings:

```
Memory Policy:     Default Conservative
Memory Profile:    General Knowledge
Default Scope:     User
Retrieval Mode:    Hybrid
Max Items:         5
Token Budget:      1000
```

5. Save the agent

### Step 3: Test Memory Capture

1. Open the **Agent Chat** for your agent
2. Have a conversation and mention something memorable:
   > "By the way, my name is Alice and I work in marketing."

3. End the conversation (or wait for idle timeout)
4. Check **HUF > Memory > Memory Record**
5. You should see a new memory record created

### Step 4: Test Memory Retrieval

1. Start a new conversation with the same agent
2. Ask something that requires memory:
   > "What do you know about me?"

3. The agent should recall your name and job from the previous conversation

## Configuration Walkthrough

### Choosing a Memory Profile

Profiles determine what type of information is captured:

| Use Case | Recommended Profile |
|----------|---------------------|
| General chatbot | General Knowledge |
| Coding assistant | Programming |
| Customer support | CRM |
| Documentation bot | Documentation |
| Research assistant | Science/Research |
| Travel planner | Travel Planning |
| Language tutor | Language Learning |

### Choosing a Memory Policy

Policies control capture behavior:

| Policy | Best For | Trade-off |
|--------|----------|-----------|
| **Default Conservative** | Production use | High quality, fewer memories |
| **Default Aggressive** | Development/testing | More memories, may include noise |
| **Default Rules-Only** | Performance-critical | Fast, deterministic, limited flexibility |

### Understanding Scope

Scope controls memory visibility:

```
Conversation: Only visible in the current chat
              ↓ Close chat, memory is "forgotten"

User:         Shared across all user's conversations with this agent
              ↓ Perfect for personal preferences

Agent:        All users share the same memory pool
              ↓ Good for accumulated knowledge

Namespace:    Shared across a group of agents
              ↓ For multi-agent workflows

Global:       All agents, all users
              ↓ Use sparingly
```

## Common Configurations

### Configuration 1: Personal Assistant

```yaml
Profile: General Knowledge
Policy: Default Conservative
Scope: User
Retrieval: Hybrid
Use Case: Remember user preferences, facts, and history across sessions
```

### Configuration 2: Coding Assistant

```yaml
Profile: Programming
Policy: Default Aggressive
Scope: User
Retrieval: Inject
Use Case: Remember code patterns, tech stack, debugging approaches
```

### Configuration 3: Support Bot

```yaml
Profile: CRM
Policy: Default Conservative
Scope: User
Retrieval: Hybrid
Use Case: Track customer interactions, issues, resolutions
```

### Configuration 4: Knowledge Base

```yaml
Profile: Documentation
Policy: Default Conservative
Scope: Namespace
Retrieval: Tool Only
Use Case: Query documentation via memory search tool
```

## Troubleshooting

### Memories Not Being Created

1. **Check policy is enabled**: Go to Memory Policy, verify "Enabled" is checked
2. **Check capture frequency**: If set to "conversation_end", memories only create when conversation closes
3. **Check confidence threshold**: If too high (0.9+), many captures may be rejected
4. **Check scope**: Verify the scope_key template is generating valid keys

### Memories Not Being Retrieved

1. **Check retrieval mode**: If "tool_only", agent must explicitly search
2. **Check scope**: Memories in "conversation" scope won't be found in new chats
3. **Check indexing**: Verify FTS or Vector index is enabled and built
4. **Check token budget**: If budget is too low, memories may be filtered out

### Too Many/Few Memories

| Problem | Solution |
|---------|----------|
| Too many low-quality memories | Increase min_confidence, use stricter policy |
| Too few memories | Lower min_confidence, use aggressive policy |
| Wrong information captured | Refine capture_prompt or use structured schema |
| Duplicates | Enable allow_update_existing, allow_merge |

## Next Steps

- Learn about [Memory Profiles](./profiles.md) and how to customize them
- Understand [Capture Modes](./capture-modes.md) for fine-grained control
- Explore the [API Reference](./api-reference.md) for programmatic access
- Review [Best Practices](./best-practices.md) for production deployments