# HUF Memory System Documentation

Welcome to the HUF Memory System documentation. This comprehensive guide covers everything you need to know about adding persistent memory capabilities to your HUF agents.

## Quick Navigation

| Document | Description |
|----------|-------------|
| [Overview](./overview.md) | Mental model, architecture, and key concepts |
| [Getting Started](./getting-started.md) | Quick start guide for first-time users |
| [Profiles](./profiles.md) | Memory profile documentation and examples |
| [Capture Modes](./capture-modes.md) | How and when memories are captured |
| [Retrieval](./retrieval.md) | Search, ranking, and injection mechanisms |
| [API Reference](./api-reference.md) | Complete Python and frontend API reference |
| [Best Practices](./best-practices.md) | Production recommendations and troubleshooting |

## What is the Memory System?

The HUF Memory System gives AI agents long-term memory. Instead of treating every conversation as isolated, agents can:

- **Remember** user preferences and facts across sessions
- **Learn** from past interactions
- **Build** persistent context over time
- **Provide** personalized experiences

Think of it as the difference between talking to someone with amnesia versus a friend who remembers your history together.

## Core Concepts

```
┌─────────────────────────────────────────────────────────────┐
│  Conversation → Capture → Storage → Index → Retrieve → Use │
└─────────────────────────────────────────────────────────────┘
```

### Memory Record
A single piece of remembered information with structured data.

### Memory Profile
Defines the "shape" of memories for specific domains (Programming, CRM, Travel, etc.)

### Memory Policy
Controls when and how memories are captured (frequency, quality, storage options)

### Scope
Determines who can access a memory (conversation, user, agent, namespace, global)

## Getting Started in 5 Minutes

1. **Verify Installation**: Check that default profiles and policies exist
2. **Enable Memory**: Turn on memory for an agent
3. **Test Capture**: Have a conversation and check for created memories
4. **Test Retrieval**: Start a new conversation and verify memories are recalled

See [Getting Started](./getting-started.md) for detailed steps.

## Default Profiles

The system comes with 7 built-in profiles:

| Profile | Purpose |
|---------|---------|
| Programming | Code patterns, tech stack, debugging |
| General Knowledge | Everyday facts, preferences, topics |
| Travel Planning | Destinations, bookings, preferences |
| Documentation | Technical docs, APIs, guides |
| Science/Research | Hypotheses, findings, citations |
| Language Learning | Vocabulary, grammar, progress |
| CRM | Customer interactions, deals, follow-ups |

## Example Use Cases

### Personal Assistant
```yaml
Profile: General Knowledge
Policy: Default Conservative
Scope: User
```
Remembers user preferences, facts, and history across all conversations.

### Coding Assistant
```yaml
Profile: Programming
Policy: Default Aggressive
Scope: User
```
Captures code patterns, tech stack preferences, and debugging approaches.

### Support Bot
```yaml
Profile: CRM
Policy: Default Conservative
Scope: User
```
Tracks customer interactions, issues, and resolutions.

### Knowledge Base
```yaml
Profile: Documentation
Policy: Default Conservative
Scope: Namespace
Retrieval: Tool Only
```
Allows querying documentation via memory search tool.

## Architecture Highlights

- **Capture Pipeline**: Extract memories using various strategies (main agent, dedicated agent, post-run LLM, rules-only)
- **Storage Layer**: MariaDB with optional FTS and vector indexes
- **Retrieval System**: Keyword, semantic, and hybrid search with ranking
- **Injection System**: Automatic or on-demand memory inclusion in prompts

## API Quick Reference

### Python
```python
# Search memories
from huf.huf.memory.search import search_memories
results = search_memories(query="user preferences", agent="my-agent")

# Create memory programmatically
from huf.huf.memory.storage import create_memory
memory = create_memory(
    title="User preference",
    memory_type="preference",
    data={"theme": "dark"},
    agent="my-agent",
    scope_type="user",
    scope_key="user_123"
)
```

### TypeScript/React
```typescript
// Search hook
const { searchMemories } = useMemory();
const results = await searchMemories({ query: "preferences" });

// Create memory
const { createMemory } = useMemory();
await createMemory({
  title: "New preference",
  memory_type: "preference",
  data: { theme: "dark" }
});
```

## Support

For issues, questions, or contributions:

1. Check the [troubleshooting section](./best-practices.md#troubleshooting)
2. Review the [API Reference](./api-reference.md)
3. Consult the [Best Practices](./best-practices.md)

## Contributing

Contributions to the Memory System are welcome! Areas for contribution:

- New memory profiles
- Additional capture modes
- Improved retrieval algorithms
- Better documentation
- Bug fixes

## License

Part of the HUF project. See main repository for license information.