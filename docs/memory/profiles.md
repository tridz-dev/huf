# Memory Profiles

Memory Profiles define the **structure** and **behavior** of memories for specific domains. Think of them as templates that tell the system what information to capture and how to organize it.

## Built-in Profiles

### 1. Programming Profile

**Purpose**: Code-related conversations, development workflows, technical discussions

**Schema Structure**:
```json
{
  "code_patterns": ["reusable patterns or idioms"],
  "tech_stack": ["technologies, frameworks, languages"],
  "coding_preferences": {"style preferences and conventions"},
  "debugging_context": {"ongoing debugging sessions or issues"},
  "architectural_decisions": ["key choices and rationale"]
}
```

**Default Capture Prompt**:
```
Extract programming-related memories from this conversation. Focus on:
1. Code patterns, algorithms, or solutions discussed
2. Technology preferences and constraints
3. Architectural decisions and their rationale
4. Debugging approaches that worked
5. Development workflows and preferences
```

**Recommended For**:
- Coding assistants
- Code review bots
- Technical documentation agents
- DevOps automation

**Example Memories**:
- "User prefers TypeScript over JavaScript for new projects"
- "Project uses Docker Compose with 3 services: web, db, cache"
- "Debugging approach: check logs → reproduce → isolate → fix"

---

### 2. General Knowledge Profile

**Purpose**: Everyday conversations, personal information, general facts

**Schema Structure**:
```json
{
  "facts": [
    {"subject": "...", "predicate": "...", "confidence": 0.95}
  ],
  "topics": ["discussed topics"],
  "interests": ["user interests discovered"],
  "questions": ["questions asked by user"]
}
```

**Default Capture Prompt**:
```
Extract key information from this conversation. Capture:
1. Important facts mentioned
2. Topics of interest to the user
3. Questions that were asked
4. Preferences expressed
5. Any commitments or follow-ups
```

**Recommended For**:
- Personal assistants
- General chatbots
- Companion AI
- Life coaching agents

**Example Memories**:
- "User lives in Seattle, works remotely"
- "Interested in hiking and photography"
- "Prefers morning meetings over afternoon"

---

### 3. Travel Planning Profile

**Purpose**: Trip planning, destination research, itinerary management

**Schema Structure**:
```json
{
  "destinations": ["places being considered or visited"],
  "dates": {
    "departure": "2026-06-15",
    "return": "2026-06-22",
    "flexibility": "±2 days"
  },
  "travelers": {
    "count": 2,
    "composition": "couple",
    "special_requirements": ["wheelchair accessible"]
  },
  "preferences": {
    "accommodation": "boutique hotel",
    "activities": ["museums", "hiking", "food tours"],
    "budget_range": "mid-range",
    "dietary": ["vegetarian"]
  },
  "bookings": [
    {"type": "flight", "details": {}, "confirmation": "ABC123"}
  ]
}
```

**Recommended For**:
- Travel agents
- Vacation planners
- Trip assistants
- Booking bots

**Example Memories**:
- "Planning trip to Japan, 2 weeks, May 2026"
- "Prefers ryokan over hotels when available"
- "Must-see: Tokyo, Kyoto, Osaka"

---

### 4. Documentation Profile

**Purpose**: Technical documentation, knowledge base articles, reference material

**Schema Structure**:
```json
{
  "document_type": "api_reference|tutorial|guide|faq|changelog|concept",
  "title": "...",
  "summary": "...",
  "sections": [
    {
      "heading": "...",
      "content": "...",
      "code_examples": ["..."]
    }
  ],
  "related_topics": ["..."],
  "tags": ["..."],
  "version": "1.0.0",
  "last_updated": "2026-03-28T10:00:00Z"
}
```

**Recommended For**:
- Documentation generators
- Knowledge base assistants
- API documentation bots
- Tutorial creators

**Example Memories**:
- "API endpoint /users supports GET, POST, PUT, DELETE"
- "Authentication requires Bearer token in Authorization header"
- "Rate limit: 100 requests per minute"

---

### 5. Science/Research Profile

**Purpose**: Scientific discussions, research analysis, academic work

**Schema Structure**:
```json
{
  "research_topic": "...",
  "hypothesis": "...",
  "methodology": "...",
  "findings": ["..."],
  "data_points": [
    {"metric": "...", "value": "...", "unit": "...", "uncertainty": "..."}
  ],
  "citations": [
    {"authors": "...", "title": "...", "year": 2026, "doi": "..."}
  ],
  "conclusions": "...",
  "future_work": ["..."]
}
```

**Recommended For**:
- Research assistants
- Literature review bots
- Data analysis agents
- Academic writing helpers

**Example Memories**:
- "Experiment shows 15% improvement with new method (p<0.05)"
- "Key paper: Smith et al. (2025) on neural network optimization"
- "Future work: test with larger dataset, different demographics"

---

### 6. Language Learning Profile

**Purpose**: Language learning conversations, vocabulary tracking, progress monitoring

**Schema Structure**:
```json
{
  "target_language": "Spanish",
  "native_language": "English",
  "proficiency_level": "intermediate",
  "vocabulary": [
    {
      "word": "biblioteca",
      "translation": "library",
      "context": "La biblioteca está cerrada",
      "part_of_speech": "noun"
    }
  ],
  "phrases": [
    {"phrase": "...", "meaning": "...", "usage_context": "..."}
  ],
  "grammar_points": [
    {"rule": "...", "explanation": "...", "examples": ["..."]}
  ],
  "mistakes": [
    {"error": "...", "correction": "...", "explanation": "..."}
  ],
  "learning_goals": ["..."]
}
```

**Recommended For**:
- Language tutors
- Vocabulary trackers
- Grammar assistants
- Conversation practice bots

**Example Memories**:
- "Learned 10 new Spanish words today"
- "Common mistake: using 'ser' instead of 'estar' for location"
- "Goal: hold 5-minute conversation by end of month"

---

### 7. CRM Profile

**Purpose**: Customer relationship management, sales, support interactions

**Schema Structure**:
```json
{
  "contact": {
    "name": "...",
    "email": "...",
    "phone": "...",
    "company": "...",
    "title": "..."
  },
  "interaction_type": "call|email|meeting|demo|support|follow_up",
  "opportunity": {
    "name": "...",
    "value": 50000,
    "currency": "USD",
    "stage": "negotiation",
    "probability": 0.7,
    "expected_close": "2026-04-15"
  },
  "key_points": ["..."],
  "pain_points": ["..."],
  "next_steps": ["..."],
  "follow_up_date": "2026-04-01",
  "sentiment": "positive"
}
```

**Recommended For**:
- Sales assistants
- Customer support bots
- Account management agents
- Lead qualification tools

**Example Memories**:
- "Contact: John Doe, CTO at Acme Inc, interested in enterprise plan"
- "Pain point: current solution too expensive, needs better reporting"
- "Next step: demo scheduled for Thursday, send case studies before"

---

## Creating Custom Profiles

### Step 1: Define Your Schema

Create a JSON Schema that describes the structure of memories you want:

```json
{
  "type": "object",
  "properties": {
    "customer_id": {"type": "string"},
    "preferences": {
      "type": "object",
      "properties": {
        "communication_channel": {"type": "string", "enum": ["email", "phone", "chat"]},
        "best_time_to_contact": {"type": "string"}
      }
    },
    "history": {
      "type": "array",
      "items": {"type": "string"}
    }
  },
  "required": ["customer_id"]
}
```

### Step 2: Write a Capture Prompt

Create a prompt that guides the LLM on what to extract:

```
Extract customer interaction details from this conversation:
1. Customer identification information
2. Communication preferences
3. Key discussion points
4. Any complaints or praise
5. Follow-up actions agreed upon

Format as structured JSON matching the provided schema.
```

### Step 3: Create the Profile

1. Go to **HUF > Memory > Memory Profile**
2. Click **New**
3. Fill in:
   - Profile Name: "Customer Service"
   - Category: "support"
   - Default Schema: (paste your JSON)
   - Capture Prompt: (paste your prompt)
4. Configure other defaults as needed
5. Save

### Step 4: Test

1. Create a memory policy using your new profile
2. Assign to an agent
3. Test with sample conversations
4. Review captured memories and refine

## Profile Best Practices

### 1. Keep Schemas Focused

Don't try to capture everything. Focus on 3-5 key fields:

```json
// GOOD: Focused
{
  "product_interest": "...",
  "budget_range": "...",
  "timeline": "..."
}

// BAD: Too broad
{
  "everything_about_customer": "...",
  "all_preferences": "...",
  "complete_history": "..."
}
```

### 2. Use Meaningful Field Names

```json
// GOOD: Clear
{
  "preferred_contact_time": "morning",
  "timezone": "America/New_York"
}

// BAD: Ambiguous
{
  "time": "morning",
  "location": "America/New_York"
}
```

### 3. Include Examples in Prompts

```
Extract preferences. Examples of good extractions:
- "User prefers email over phone" → {"channel": "email"}
- "Available weekdays 9-5 EST" → {"availability": "weekdays", "hours": "9-5", "timezone": "EST"}
```

### 4. Set Appropriate Defaults

| Setting | Recommendation |
|---------|----------------|
| Capture Stage | `post_response_async` for non-blocking |
| Frequency | `conversation_end` for summaries |
| Scope | `user` for personal info, `agent` for general knowledge |
| Indexing | `both` for best search results |

## Profile Comparison

| Profile | Structured | Best Retrieval | Storage Size |
|---------|------------|----------------|--------------|
| Programming | High | Hybrid | Medium |
| General Knowledge | Medium | Inject | Medium |
| Travel | High | Hybrid | Large |
| Documentation | High | Tool Only | Large |
| Science/Research | High | Hybrid | Medium |
| Language Learning | High | Inject | Large |
| CRM | High | Inject | Medium |

## Next Steps

- Learn about [Capture Modes](./capture-modes.md) to control when memories are extracted
- Understand [Retrieval](./retrieval.md) mechanisms for accessing memories
- Review [Best Practices](./best-practices.md) for production deployments