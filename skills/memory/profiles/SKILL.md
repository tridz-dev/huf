# Skill: Memory Profiles

Create and use opinionated memory profiles for common domains.

## Overview

Memory profiles provide ready-made capture schemas, prompts, and configuration for specific use cases. They make memory setup faster and more consistent.

## Built-in Profiles

### 1. Programming Memory

**Purpose**: Code patterns, conventions, debugging context, architectural decisions

**Schema**:
```json
{
    "memory_type": "code_pattern|convention|debugging|architecture|api_usage",
    "title": "string",
    "content": "string",
    "language": "string",
    "framework": "string",
    "tags": ["string"],
    "confidence": "number"
}
```

**Defaults**:
- Capture stage: `post_response_async`
- Frequency: `every_n_turns`
- Scope: `agent`
- Indexing: `fts`
- Retrieval: `inject`

**Example**:
```python
from huf.memory.profiles import get_profile_by_category

profile = get_profile_by_category("programming")
schema = profile.get_schema()
prompt = profile.get_capture_prompt()
```

### 2. General Knowledge Memory

**Purpose**: Facts, preferences, habits, references

**Schema**:
```json
{
    "memory_type": "fact|preference|habit|reference",
    "title": "string",
    "content": "string",
    "category": "string",
    "importance": "number",
    "confidence": "number"
}
```

**Defaults**:
- Capture stage: `conversation_end`
- Frequency: `conversation_end`
- Scope: `user`
- Indexing: `both`
- Retrieval: `hybrid`

### 3. Travel Planning Memory

**Purpose**: Destinations, dates, preferences, constraints

**Schema**:
```json
{
    "memory_type": "destination|date|preference|constraint|booking",
    "title": "string",
    "content": "string",
    "location": "string",
    "dates": {
        "start": "string",
        "end": "string"
    },
    "budget": "string",
    "travelers": "number",
    "confidence": "number"
}
```

**Defaults**:
- Capture stage: `in_prompt`
- Frequency: `every_run`
- Scope: `conversation`
- Indexing: `fts`
- Retrieval: `inject`

### 4. CRM Memory

**Purpose**: Customer context, interactions, opportunities

**Schema**:
```json
{
    "memory_type": "customer_info|interaction|preference|issue|opportunity",
    "title": "string",
    "content": "string",
    "customer_id": "string",
    "sentiment": "positive|neutral|negative",
    "priority": "low|medium|high",
    "follow_up_required": "boolean",
    "confidence": "number"
}
```

**Defaults**:
- Capture stage: `post_response_async`
- Frequency: `every_run`
- Scope: `namespace`
- Indexing: `both`
- Retrieval: `hybrid`

### 5. Documentation Memory

**Purpose**: Requirements, decisions, API contracts, specifications

**Schema**:
```json
{
    "memory_type": "requirement|decision|api_contract|spec|note",
    "title": "string",
    "content": "string",
    "project": "string",
    "status": "draft|approved|deprecated",
    "stakeholders": ["string"],
    "related_docs": ["string"],
    "confidence": "number"
}
```

**Defaults**:
- Capture stage: `conversation_end`
- Frequency: `conversation_end`
- Scope: `namespace`
- Indexing: `both`
- Retrieval: `hybrid`

## Using Profiles

### Apply Profile to Agent

```python
# In Agent DocType
{
    "enable_memory": True,
    "memory_profile": "Programming Memory",
    "memory_policy": "my-policy"
}
```

### Create Memory Policy from Profile

```python
from huf.huf.doctype.memory_profile.memory_profile import MemoryProfile

profile = frappe.get_doc("Memory Profile", "Programming Memory")

policy = frappe.new_doc("Memory Policy")
policy.update({
    "policy_name": "Programming Policy",
    "agent": "my-coding-agent",
    "memory_profile": profile.name,
    "capture_owner": "post_run_llm",
    "capture_stage": profile.default_capture_stage,
    "capture_prompt": profile.default_capture_prompt,
    "capture_schema_json": profile.default_schema_json,
    "default_scope_type": profile.default_scope_type,
    "enable_fts_index": "fts" in profile.default_indexing_mode,
    "enable_vector_index": "vector" in profile.default_indexing_mode,
    "retrieval_mode_default": profile.default_retrieval_mode
})
policy.insert()
```

### Get Schema from Profile

```python
profile = frappe.get_doc("Memory Profile", "Travel Planning Memory")
schema = profile.get_schema()
# Returns: Python dict of the schema
```

### Get Capture Prompt

```python
profile = frappe.get_doc("Memory Profile", "CRM Memory")

# Static prompt
prompt = profile.get_capture_prompt()

# With template substitution
prompt = profile.get_capture_prompt(context={
    "agent_name": "Support Bot",
    "company": "Acme Corp"
})
```

## Creating Custom Profiles

### Programmatic Creation

```python
import json
import frappe

profile = frappe.new_doc("Memory Profile")
profile.update({
    "profile_name": "E-commerce Memory",
    "description": "For capturing product preferences, orders, and shopping behavior",
    "category": "ecommerce",
    "is_system_profile": False,
    "default_schema_json": json.dumps({
        "memory_type": "product_preference|order|cart|wishlist|behavior",
        "title": "string",
        "product_id": "string",
        "category": "string",
        "price_range": {"min": "number", "max": "number"},
        "attributes": {"object": "any"},
        "confidence": "number"
    }),
    "default_capture_prompt": """Extract e-commerce related information from the conversation.

Capture:
- Product preferences and interests
- Order history mentions
- Cart additions/removals
- Wishlist items
- Shopping behavior patterns

Return structured JSON matching the schema.""",
    "default_capture_stage": "post_response_async",
    "default_frequency": "every_n_turns",
    "default_scope_type": "user",
    "default_indexing_mode": "both",
    "default_retrieval_mode": "hybrid",
    "recommended_model": "gpt-4",
    "recommended_provider": "openai"
})
profile.insert()
```

### Profile with Type Mapping

```python
profile = frappe.new_doc("Memory Profile")
profile.update({
    "profile_name": "Smart Memory",
    "default_memory_type_mapping": json.dumps({
        "code": "domain_object",
        "function": "domain_object",
        "error": "observation",
        "solution": "insight",
        "preference": "preference"
    })
})

# Infer memory type from content
type = profile.infer_memory_type("The user prefers dark mode", "text")
# Returns: "preference"
```

## Memory Types Reference

| Type | Description | Example |
|------|-------------|---------|
| `profile` | User profile information | Name, preferences, settings |
| `session_state` | Current session context | Current task, progress |
| `preference` | User preferences | Theme, language, style |
| `fact` | Factual information | User works at Acme Corp |
| `plan` | Plans or goals | Travel itinerary, project plan |
| `observation` | Observed behavior | User clicked X, said Y |
| `insight` | Derived insights | User prefers concise answers |
| `domain_object` | Domain-specific objects | Code snippets, API specs |
| `custom` | Custom/uncategorized | Any other memory |

## Profile API

```python
# Get all system profiles
from huf.huf.doctype.memory_profile.memory_profile import MemoryProfile
profiles = MemoryProfile.get_system_profiles()

# Get profile by category
profile = MemoryProfile.get_profile_by_category("travel")

# Create default profiles (setup/migration)
created = MemoryProfile.create_default_profiles()
```

## Best Practices

1. **Start with built-in profiles** - They cover common use cases
2. **Customize schemas** - Add fields relevant to your domain
3. **Set appropriate scopes** - User scope for preferences, conversation for temporary
4. **Use type mapping** - Automatically categorize memories
5. **Document custom profiles** - Add clear descriptions for team
6. **Version profiles** - Update carefully to avoid breaking existing memories
