# Programming Memory Profile

## Overview

The Programming Memory profile captures structured programming knowledge from conversations to build a persistent technical memory. It helps agents provide better assistance by remembering your coding preferences, architectural decisions, debugging insights, and reusable patterns.

## When to Use

Use this profile when:
- Discussing code or technical architecture
- Making decisions about technology choices
- Debugging issues and finding solutions
- Establishing project conventions
- Sharing reusable code snippets
- Configuring development tools

## Memory Types

### 1. Language Preferences (`language_pref`)
Captures primary language choices and version constraints.

**Captured fields:**
- Preferred language(s)
- Version requirements
- Language-specific settings

**Example use case:** Remembering the user prefers TypeScript with strict mode enabled.

---

### 2. Stack Configuration (`stack_config`)
Records the technology stack for projects.

**Captured fields:**
- Frontend framework
- Backend technology
- Database choice
- Infrastructure/platform
- Development tools

**Example use case:** Recalling a project uses Next.js + tRPC + PostgreSQL + Vercel.

---

### 3. Coding Conventions (`convention`)
Stores style preferences and project organization rules.

**Captured fields:**
- Naming conventions
- Style guide references
- Project structure patterns
- Custom linting rules

**Example use case:** Remembering the team uses snake_case for Python but camelCase for JavaScript.

---

### 4. Architectural Decisions (`architecture_decision`)
Documents significant design choices with context and rationale.

**Captured fields:**
- Decision title and context
- Options considered
- Chosen approach
- Rationale and tradeoffs
- Reversibility assessment

**Example use case:** Recording why GraphQL was chosen over REST for a specific service.

---

### 5. Fix Patterns (`fix_pattern`)
Captures reusable solutions to bugs and issues.

**Captured fields:**
- Problem description
- Identifying symptoms
- Root cause analysis
- Solution steps
- Prevention strategies

**Example use case:** Recording how to fix SQLAlchemy connection pool exhaustion in FastAPI apps.

---

### 6. Debugging Context (`debug_context`)
Stores context from debugging sessions.

**Captured fields:**
- Error messages and codes
- Environment details
- Diagnostic steps taken
- Resolution found

**Example use case:** Remembering a specific error pattern and its fix for a recurring issue.

---

### 7. Code Snippets (`snippet`)
Saves reusable code patterns and utilities.

**Captured fields:**
- Snippet title and description
- Code content
- Usage instructions
- Tags for discovery

**Example use case:** Storing a custom React hook or utility function used across projects.

---

### 8. Tool Configurations (`tool_config`)
Records editor, CLI, and environment preferences.

**Captured fields:**
- Editor/IDE settings
- CLI tool preferences
- Environment variables
- Aliases and shortcuts

**Example use case:** Remembering custom VS Code settings or shell aliases.

---

### 9. Learning & Insights (`learning`)
Captures new knowledge and best practices discovered.

**Captured fields:**
- Concepts learned
- Best practices identified
- Lessons from mistakes
- Performance insights

**Example use case:** Recording insights about async Rust patterns or new language features.

---

## Schema Reference

See `profile.json` for the complete JSON schema. Key fields for all memory types:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `memory_type` | string | Yes | One of the 9 memory type identifiers |
| `language` | string | Yes | Primary programming language |
| `importance` | enum | Yes | `critical`, `high`, `medium`, or `low` |
| `confidence` | number | Yes | 0.0 to 1.0 confidence score |
| `tags` | array | No | Searchable tags for retrieval |
| `project_context` | string | No | Project identifier for scoping |
| `related_files` | array | No | File paths mentioned in context |

## Capture Configuration

### Default Settings

| Setting | Value | Description |
|---------|-------|-------------|
| Capture Stage | `post_response_async` | Capture happens after response, asynchronously |
| Frequency | `conversation_end` | Trigger at end of conversation |
| Scope | `user` | Memory scoped to user across conversations |
| Indexing | `fts_and_vector` | Full-text and vector indexing enabled |
| Retrieval | `hybrid` | Both injection and tool-based search |

### Recommended Model

- **Primary:** Claude 3.5 Sonnet (Anthropic)
- **Fallback:** GPT-4o Mini for cost-effective extraction

## Usage Examples

### Example 1: Capturing an Architecture Decision

**Conversation:**
> User: "We're going with tRPC for the new dashboard. I evaluated REST and GraphQL but the type safety and DX win for our team size. The tradeoff is tighter coupling but we don't need mobile support yet."

**Extracted Memory:**
```json
{
  "memory_type": "architecture_decision",
  "language": "TypeScript",
  "decision": {
    "title": "Chose tRPC over REST for API layer",
    "options_considered": ["REST with OpenAPI", "GraphQL with Apollo", "tRPC"],
    "chosen_approach": "tRPC with Next.js integration",
    "rationale": "End-to-end type safety without code generation, excellent DX",
    "tradeoffs": "Tighter coupling between frontend and backend"
  },
  "importance": "critical",
  "confidence": 0.95,
  "tags": ["typescript", "trpc", "architecture"]
}
```

### Example 2: Capturing a Fix Pattern

**Conversation:**
> User: "Finally fixed that SQLAlchemy pool exhaustion. The default pool size of 5 was too small for FastAPI. Had to bump it to 20 with overflow to 40 and add pool_pre_ping. Always use explicit pool sizes with async SQLAlchemy!"

**Extracted Memory:**
```json
{
  "memory_type": "fix_pattern",
  "language": "Python",
  "fix_pattern": {
    "problem": "Database connection pool exhaustion under async load",
    "symptoms": ["TimeoutError", "QueuePool limit reached"],
    "solution": "Increase pool_size to 20, max_overflow to 40, add pool_pre_ping=True",
    "prevention": "Always set explicit pool sizes for async SQLAlchemy"
  },
  "importance": "high",
  "confidence": 0.92,
  "tags": ["python", "fastapi", "sqlalchemy", "performance"]
}
```

## Retrieval Behavior

### Injected Context

When `retrieval_mode` is `inject` or `hybrid`, relevant memories are automatically included in the agent's prompt context.

**Prioritization:**
1. Memories from the same `project_context`
2. High importance memories
3. Recently accessed memories
4. Memories matching current conversation tags

### Tool-Based Search

Agents can explicitly search memories using the `memory_search` tool with filters:
- `memory_type`: Filter by type (e.g., only `fix_pattern`)
- `language`: Filter by programming language
- `tags`: Filter by tags
- `project_context`: Filter by project

## Best Practices

1. **Use consistent project_context** - Tag memories with project identifiers to keep contexts separate
2. **Tag liberally** - Include language, framework, and domain tags for better retrieval
3. **Set appropriate importance** - Reserve "critical" for fundamental preferences and decisions
4. **Review and prune** - Periodically review memories and archive outdated ones
5. **Link related files** - Include file paths when relevant for better context

## Integration with Agents

To enable Programming Memory for an agent:

1. Set `enable_memory: true` in agent configuration
2. Set `memory_profile: "programming"`
3. Configure capture stage and frequency as needed
4. Optionally set `memory_agent` for specialized extraction

## File Structure

```
~/code/huf-memory/profiles/programming/
├── profile.json          # Profile definition and schema
├── capture_prompt.txt    # LLM prompt for extraction
├── example_records.json  # Example memory records
└── README.md            # This documentation
```

## Related Profiles

- **Documentation Memory** - For capturing documentation and requirements
- **Science/Research Memory** - For academic and research contexts
- **Language Learning Memory** - For natural language learning

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-28 | Initial release with 9 memory types |
