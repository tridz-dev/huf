"""
Default Memory Profiles for HUF Memory System

These are opinionated, production-ready profiles that ship with the system.
Users can use them as-is, customize them, or create their own.
"""

from typing import Dict, Any


# =============================================================================
# 1. PROGRAMMING MEMORY PROFILE
# =============================================================================
PROGRAMMING_MEMORY_PROFILE: Dict[str, Any] = {
    "profile_name": "Programming Memory",
    "description": "Captures code patterns, debugging context, architectural decisions, and technical preferences. Optimized for software development workflows.",
    "category": "Programming",
    "icon": "💻",
    "is_system_profile": 1,
    
    "default_schema_json": {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": ["code_pattern", "debugging_context", "architecture_decision", "tech_preference", "error_solution", "api_usage", "refactoring_note"],
                "description": "Type of programming memory"
            },
            "title": {
                "type": "string",
                "description": "Short, descriptive title"
            },
            "context": {
                "type": "string",
                "description": "When/where this applies"
            },
            "details": {
                "type": "string",
                "description": "The actual memory content"
            },
            "code_snippet": {
                "type": "string",
                "description": "Relevant code example if applicable"
            },
            "language": {
                "type": "string",
                "description": "Programming language or framework"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relevant tags (e.g., ['react', 'performance', 'bugfix'])"
            },
            "importance": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low"],
                "description": "How important this memory is"
            }
        },
        "required": ["memory_type", "title", "details"]
    },
    
    "default_capture_prompt": """Extract programming-related memories from this conversation. Focus on:

1. **Code Patterns**: Reusable code snippets, design patterns, architectural approaches
2. **Debugging Context**: Error solutions, root causes, troubleshooting steps
3. **Technical Preferences**: Style preferences, library choices, configuration decisions
4. **Architecture Decisions**: Why certain approaches were chosen over alternatives
5. **API Usage**: Important API patterns, endpoints, authentication methods

Guidelines:
- Capture concrete, actionable information
- Include code snippets when relevant
- Note the programming language/framework
- Tag with relevant technologies
- Assess importance based on reusability

Return a JSON object matching the schema. If nothing worth remembering, return {"skip": true}.""",

    "default_memory_type_mapping": {
        "conversation": "insight",
        "run": "observation",
        "manual": "custom",
        "event": "observation"
    },
    
    "recommended_model": "claude-3-sonnet",
    "recommended_provider": "anthropic",
    
    "default_capture_stage": "post_response_async",
    "default_frequency": "every_n_turns",
    "default_scope_type": "agent",
    "default_indexing_mode": "fts_and_vector",
    "default_retrieval_mode": "hybrid",
    
    "ui_labels_json": {
        "memory_type_labels": {
            "code_pattern": "Code Pattern",
            "debugging_context": "Debugging Context",
            "architecture_decision": "Architecture Decision",
            "tech_preference": "Technical Preference",
            "error_solution": "Error Solution",
            "api_usage": "API Usage",
            "refactoring_note": "Refactoring Note"
        },
        "field_help": {
            "code_snippet": "Paste the relevant code example here",
            "language": "e.g., Python, React, Rust, SQL",
            "tags": "Comma-separated tags for organization"
        }
    },
    
    "example_memories_json": [
        {
            "memory_type": "code_pattern",
            "title": "React useCallback for expensive calculations",
            "context": "When rendering large lists with complex item calculations",
            "details": "Use useCallback to memoize expensive calculations in list items to prevent re-computation on every render",
            "code_snippet": "const expensiveValue = useCallback(() => computeExpensive(data), [data]);",
            "language": "React/TypeScript",
            "tags": ["react", "performance", "hooks"],
            "importance": "high"
        },
        {
            "memory_type": "error_solution",
            "title": "PostgreSQL connection pooling with asyncpg",
            "context": "Database connection issues under high load",
            "details": "Always use connection pooling with asyncpg. Create pool once at startup, not per request.",
            "code_snippet": "pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)",
            "language": "Python",
            "tags": ["postgresql", "asyncpg", "database", "performance"],
            "importance": "critical"
        }
    ],
    
    "documentation_url": "/docs/memory/profiles/programming"
}


# =============================================================================
# 2. GENERAL KNOWLEDGE MEMORY PROFILE
# =============================================================================
GENERAL_KNOWLEDGE_PROFILE: Dict[str, Any] = {
    "profile_name": "General Knowledge Memory",
    "description": "Captures facts, preferences, reusable information, and learned insights. The default profile for general-purpose memory capture.",
    "category": "General Knowledge",
    "icon": "🧠",
    "is_system_profile": 1,
    
    "default_schema_json": {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": ["fact", "preference", "insight", "habit", "relationship", "goal", "lesson_learned"],
                "description": "Type of knowledge memory"
            },
            "title": {
                "type": "string",
                "description": "Short, descriptive title"
            },
            "content": {
                "type": "string",
                "description": "The actual information to remember"
            },
            "context": {
                "type": "string",
                "description": "When/where this is relevant"
            },
            "source": {
                "type": "string",
                "description": "Where this information came from"
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Confidence level (0-1)"
            },
            "category": {
                "type": "string",
                "description": "General category (e.g., work, personal, health)"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relevant tags"
            },
            "expires": {
                "type": "string",
                "format": "date",
                "description": "Optional expiration date if time-sensitive"
            }
        },
        "required": ["memory_type", "title", "content"]
    },
    
    "default_capture_prompt": """Extract useful information from this conversation that should be remembered for future reference. Focus on:

1. **Facts**: Specific information, data points, references
2. **Preferences**: Likes, dislikes, choices, priorities
3. **Insights**: Realizations, conclusions, patterns noticed
4. **Habits**: Routines, recurring behaviors, typical approaches
5. **Relationships**: Connections between people, concepts, or entities
6. **Goals**: Objectives, targets, aspirations mentioned
7. **Lessons Learned**: Takeaways from experiences

Guidelines:
- Capture information that would be useful in future conversations
- Note the context where this information applies
- Include confidence level if uncertain
- Tag with relevant categories
- Set expiration for time-sensitive information

Return a JSON object matching the schema. If nothing worth remembering, return {"skip": true}.""",

    "default_memory_type_mapping": {
        "conversation": "insight",
        "run": "fact",
        "manual": "custom",
        "event": "observation"
    },
    
    "recommended_model": "gpt-4",
    "recommended_provider": "openai",
    
    "default_capture_stage": "post_response_async",
    "default_frequency": "conversation_end",
    "default_scope_type": "user",
    "default_indexing_mode": "fts_only",
    "default_retrieval_mode": "hybrid",
    
    "ui_labels_json": {
        "memory_type_labels": {
            "fact": "Fact",
            "preference": "Preference",
            "insight": "Insight",
            "habit": "Habit",
            "relationship": "Relationship",
            "goal": "Goal",
            "lesson_learned": "Lesson Learned"
        },
        "field_help": {
            "content": "The main information to remember",
            "context": "When would this be relevant?",
            "confidence": "How certain are you about this? (0-1)"
        }
    },
    
    "example_memories_json": [
        {
            "memory_type": "preference",
            "title": "Prefers detailed technical explanations",
            "content": "User appreciates in-depth technical details rather than high-level summaries",
            "context": "When explaining how things work",
            "category": "communication",
            "tags": ["preferences", "communication_style"],
            "confidence": 0.9
        },
        {
            "memory_type": "fact",
            "title": "Working on machine learning project",
            "content": "Currently building a recommendation system using collaborative filtering",
            "context": "Relevant when discussing ML, recommendations, or current work",
            "category": "work",
            "tags": ["ml", "project", "recommendation_system"],
            "confidence": 1.0
        }
    ],
    
    "documentation_url": "/docs/memory/profiles/general-knowledge"
}


# =============================================================================
# 3. TRAVEL PLANNING MEMORY PROFILE
# =============================================================================
TRAVEL_PLANNING_PROFILE: Dict[str, Any] = {
    "profile_name": "Travel Planning Memory",
    "description": "Captures travel preferences, destination information, itineraries, and trip-related constraints. Optimized for planning and organizing travel.",
    "category": "Travel Planning",
    "icon": "✈️",
    "is_system_profile": 1,
    
    "default_schema_json": {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": ["destination", "itinerary", "preference", "constraint", "booking", "tip", "contact"],
                "description": "Type of travel memory"
            },
            "title": {
                "type": "string",
                "description": "Short, descriptive title"
            },
            "destination": {
                "type": "string",
                "description": "Location this relates to"
            },
            "dates": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "format": "date"},
                    "end": {"type": "string", "format": "date"},
                    "flexible": {"type": "boolean"}
                },
                "description": "When this applies"
            },
            "details": {
                "type": "string",
                "description": "The main information"
            },
            "budget": {
                "type": "object",
                "properties": {
                    "currency": {"type": "string"},
                    "amount": {"type": "number"},
                    "per": {"type": "string", "enum": ["total", "person", "night", "day"]}
                },
                "description": "Budget information if relevant"
            },
            "contacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "phone": {"type": "string"},
                        "email": {"type": "string"}
                    }
                },
                "description": "Relevant contacts"
            },
            "links": {
                "type": "array",
                "items": {"type": "string"},
                "description": "URLs to bookings, guides, etc."
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags like ['beach', 'family', 'budget']"
            },
            "priority": {
                "type": "string",
                "enum": ["must_do", "nice_to_have", "backup_option"],
                "description": "Priority level"
            }
        },
        "required": ["memory_type", "title", "details"]
    },
    
    "default_capture_prompt": """Extract travel-related information from this conversation. Focus on:

1. **Destinations**: Places to visit, attractions, neighborhoods
2. **Itineraries**: Day-by-day plans, schedules, routes
3. **Preferences**: Travel style, accommodation preferences, activity likes/dislikes
4. **Constraints**: Budget limits, time restrictions, accessibility needs, dietary requirements
5. **Bookings**: Reservations, confirmations, booking references
6. **Tips**: Local advice, best times, hidden gems, warnings
7. **Contacts**: Hotels, tour operators, emergency contacts

Guidelines:
- Capture specific dates and times when mentioned
- Note budget information with currency
- Include contact details for bookings
- Tag with travel style (budget, luxury, family, solo, etc.)
- Prioritize must-do items vs nice-to-have
- Include booking links and references

Return a JSON object matching the schema. If nothing travel-related, return {"skip": true}.""",

    "default_memory_type_mapping": {
        "conversation": "insight",
        "run": "observation",
        "manual": "custom",
        "event": "observation"
    },
    
    "recommended_model": "gpt-4",
    "recommended_provider": "openai",
    
    "default_capture_stage": "post_response_async",
    "default_frequency": "every_n_turns",
    "default_scope_type": "user",
    "default_indexing_mode": "fts_only",
    "default_retrieval_mode": "hybrid",
    
    "ui_labels_json": {
        "memory_type_labels": {
            "destination": "Destination",
            "itinerary": "Itinerary",
            "preference": "Travel Preference",
            "constraint": "Constraint/Requirement",
            "booking": "Booking/Reservation",
            "tip": "Travel Tip",
            "contact": "Contact Info"
        },
        "field_help": {
            "destination": "City, country, or specific location",
            "dates": "When does this apply?",
            "priority": "Is this a must-do or optional?"
        }
    },
    
    "example_memories_json": [
        {
            "memory_type": "preference",
            "title": "Prefers boutique hotels over chains",
            "details": "Likes unique, locally-owned accommodations with character. Avoids large hotel chains.",
            "tags": ["accommodation", "preference", "boutique"],
            "priority": "nice_to_have"
        },
        {
            "memory_type": "destination",
            "title": "Kyoto - Fushimi Inari Shrine",
            "destination": "Kyoto, Japan",
            "details": "Famous shrine with thousands of vermilion torii gates. Best visited early morning (before 8am) to avoid crowds.",
            "tags": ["japan", "kyoto", "temple", "early_morning"],
            "priority": "must_do"
        },
        {
            "memory_type": "constraint",
            "title": "Vegetarian dietary requirement",
            "details": "Strict vegetarian (no meat, fish, or seafood). Need to confirm vegetarian options when booking restaurants.",
            "tags": ["dietary", "vegetarian", "restaurant"],
            "priority": "must_do"
        }
    ],
    
    "documentation_url": "/docs/memory/profiles/travel"
}


# =============================================================================
# 4. CRM MEMORY PROFILE
# =============================================================================
CRM_PROFILE: Dict[str, Any] = {
    "profile_name": "CRM Memory",
    "description": "Captures customer context, interaction history, preferences, and relationship details. Optimized for sales and customer relationship management.",
    "category": "CRM/Customer Context",
    "icon": "👥",
    "is_system_profile": 1,
    
    "default_schema_json": {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": ["customer_profile", "interaction", "preference", "opportunity", "issue", "decision_maker", "competitor_mention"],
                "description": "Type of CRM memory"
            },
            "title": {
                "type": "string",
                "description": "Short, descriptive title"
            },
            "customer": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "company": {"type": "string"},
                    "role": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"}
                },
                "description": "Customer information"
            },
            "details": {
                "type": "string",
                "description": "The main information to remember"
            },
            "sentiment": {
                "type": "string",
                "enum": ["very_positive", "positive", "neutral", "negative", "very_negative"],
                "description": "Sentiment of the interaction or information"
            },
            "priority": {
                "type": "string",
                "enum": ["urgent", "high", "medium", "low"],
                "description": "Priority level"
            },
            "follow_up": {
                "type": "object",
                "properties": {
                    "needed": {"type": "boolean"},
                    "by_when": {"type": "string", "format": "date"},
                    "action": {"type": "string"}
                },
                "description": "Follow-up requirements"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags like ['hot_lead', 'enterprise', 'renewal']"
            },
            "deal_value": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "probability": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "description": "Deal/opportunity value if applicable"
            }
        },
        "required": ["memory_type", "title", "details"]
    },
    
    "default_capture_prompt": """Extract customer relationship information from this conversation. Focus on:

1. **Customer Profiles**: Background, role, company, decision-making authority
2. **Interactions**: Meeting notes, call summaries, email exchanges
3. **Preferences**: Communication preferences, product interests, buying criteria
4. **Opportunities**: Potential deals, expansion possibilities, upsell chances
5. **Issues**: Complaints, problems, concerns that need addressing
6. **Decision Makers**: Key stakeholders, influencers, budget holders
7. **Competitor Mentions**: When competitors are discussed, what was said

Guidelines:
- Record sentiment and tone of interactions
- Note any commitments or promises made
- Flag urgent follow-ups with dates
- Estimate deal values and probabilities when discussed
- Tag with pipeline stage (prospect, qualified, proposal, negotiation, closed)
- Capture communication preferences (email, phone, meeting times)

Return a JSON object matching the schema. If nothing CRM-related, return {"skip": true}.""",

    "default_memory_type_mapping": {
        "conversation": "insight",
        "run": "observation",
        "manual": "custom",
        "event": "observation"
    },
    
    "recommended_model": "claude-3-sonnet",
    "recommended_provider": "anthropic",
    
    "default_capture_stage": "post_response_async",
    "default_frequency": "every_run",
    "default_scope_type": "namespace",
    "default_indexing_mode": "fts_and_vector",
    "default_retrieval_mode": "hybrid",
    
    "ui_labels_json": {
        "memory_type_labels": {
            "customer_profile": "Customer Profile",
            "interaction": "Interaction Note",
            "preference": "Customer Preference",
            "opportunity": "Opportunity",
            "issue": "Issue/Concern",
            "decision_maker": "Decision Maker",
            "competitor_mention": "Competitor Mention"
        },
        "field_help": {
            "customer": "Who is this about?",
            "sentiment": "Overall tone of this information",
            "follow_up": "Is action needed? By when?",
            "deal_value": "Estimated opportunity size and win probability"
        }
    },
    
    "example_memories_json": [
        {
            "memory_type": "preference",
            "title": "Prefers email over calls",
            "customer": {"name": "Sarah Chen", "company": "TechCorp", "role": "CTO"},
            "details": "Sarah prefers detailed emails with technical specifications over phone calls. Response time typically 24-48 hours.",
            "sentiment": "positive",
            "tags": ["communication_preference", "cto", "enterprise"],
            "priority": "medium"
        },
        {
            "memory_type": "opportunity",
            "title": "Q3 expansion possibility",
            "customer": {"name": "Sarah Chen", "company": "TechCorp", "role": "CTO"},
            "details": "Mentioned potential need for additional licenses in Q3. Budget discussions happening in June.",
            "sentiment": "positive",
            "deal_value": {"amount": 50000, "currency": "USD", "probability": 0.6},
            "follow_up": {"needed": true, "by_when": "2024-06-15", "action": "Send updated pricing and case studies"},
            "tags": ["expansion", "q3", "budget_cycle"],
            "priority": "high"
        }
    ],
    
    "documentation_url": "/docs/memory/profiles/crm"
}


# =============================================================================
# 5. DOCUMENTATION MEMORY PROFILE
# =============================================================================
DOCUMENTATION_PROFILE: Dict[str, Any] = {
    "profile_name": "Documentation Memory",
    "description": "Captures requirements, decisions, API contracts, and knowledge base articles. Optimized for technical documentation and knowledge management.",
    "category": "Documentation",
    "icon": "📚",
    "is_system_profile": 1,
    
    "default_schema_json": {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": ["requirement", "decision", "api_contract", "process", "definition", "how_to", "troubleshooting", "reference"],
                "description": "Type of documentation"
            },
            "title": {
                "type": "string",
                "description": "Clear, descriptive title"
            },
            "content": {
                "type": "string",
                "description": "The main documentation content"
            },
            "project": {
                "type": "string",
                "description": "Project or system this relates to"
            },
            "status": {
                "type": "string",
                "enum": ["draft", "proposed", "approved", "implemented", "deprecated"],
                "description": "Current status"
            },
            "stakeholders": {
                "type": "array",
                "items": {"type": "string"},
                "description": "People or teams involved"
            },
            "decision_context": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string"},
                    "options_considered": {"type": "array", "items": {"type": "string"}},
                    "chosen_option": {"type": "string"},
                    "rationale": {"type": "string"},
                    "tradeoffs": {"type": "string"}
                },
                "description": "For decision records (ADRs)"
            },
            "api_details": {
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                    "version": {"type": "string"},
                    "parameters": {"type": "object"},
                    "response_schema": {"type": "object"}
                },
                "description": "For API contracts"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Categories and keywords"
            },
            "related_docs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Links to related documentation"
            }
        },
        "required": ["memory_type", "title", "content"]
    },
    
    "default_capture_prompt": """Extract documentation-worthy information from this conversation. Focus on:

1. **Requirements**: Feature requests, constraints, acceptance criteria
2. **Decisions**: Architectural decisions, design choices, policy decisions (capture as ADRs)
3. **API Contracts**: Endpoint definitions, schemas, request/response formats
4. **Processes**: Workflows, procedures, standard operating procedures
5. **Definitions**: Terminology, glossary entries, concept explanations
6. **How-To Guides**: Step-by-step instructions, tutorials
7. **Troubleshooting**: Common issues and solutions, debugging steps
8. **Reference**: Facts, configurations, specifications

Guidelines:
- Write for an audience that doesn't have the full context
- Include the "why" not just the "what" for decisions
- Note the current status (draft, approved, etc.)
- Link related documentation when mentioned
- Tag with project, team, and domain
- Use clear, unambiguous language

For decisions, capture:
- What problem were we solving?
- What options did we consider?
- What did we choose and why?
- What tradeoffs did we accept?

Return a JSON object matching the schema. If nothing documentation-worthy, return {"skip": true}.""",

    "default_memory_type_mapping": {
        "conversation": "insight",
        "run": "observation",
        "manual": "custom",
        "event": "observation"
    },
    
    "recommended_model": "claude-3-opus",
    "recommended_provider": "anthropic",
    
    "default_capture_stage": "post_response_async",
    "default_frequency": "conversation_end",
    "default_scope_type": "namespace",
    "default_indexing_mode": "fts_and_vector",
    "default_retrieval_mode": "hybrid",
    
    "ui_labels_json": {
        "memory_type_labels": {
            "requirement": "Requirement",
            "decision": "Decision Record (ADR)",
            "api_contract": "API Contract",
            "process": "Process/Workflow",
            "definition": "Definition/Glossary",
            "how_to": "How-To Guide",
            "troubleshooting": "Troubleshooting",
            "reference": "Reference"
        },
        "field_help": {
            "project": "Which project or system is this about?",
            "status": "Current state of this document",
            "decision_context": "Fill this for decision records - captures the reasoning",
            "api_details": "Fill this for API documentation"
        }
    },
    
    "example_memories_json": [
        {
            "memory_type": "decision",
            "title": "ADR-042: Adopt PostgreSQL over MongoDB",
            "content": "Decision to use PostgreSQL as the primary database for the new microservice.",
            "project": "User Service",
            "status": "approved",
            "decision_context": {
                "problem": "Need a reliable database for user data with ACID compliance",
                "options_considered": ["PostgreSQL", "MongoDB", "MySQL"],
                "chosen_option": "PostgreSQL",
                "rationale": "Team has deep expertise, JSONB supports flexible schemas, strong consistency guarantees",
                "tradeoffs": "Slightly more complex scaling than MongoDB, but acceptable for our scale"
            },
            "stakeholders": ["Platform Team", "Data Team"],
            "tags": ["adr", "database", "architecture", "userservice"]
        },
        {
            "memory_type": "api_contract",
            "title": "User API - Update Profile Endpoint",
            "content": "Endpoint for updating user profile information",
            "project": "User Service",
            "status": "implemented",
            "api_details": {
                "endpoint": "/api/v1/users/{user_id}/profile",
                "method": "PATCH",
                "version": "v1",
                "parameters": {
                    "display_name": {"type": "string", "required": false},
                    "bio": {"type": "string", "maxLength": 500, "required": false},
                    "avatar_url": {"type": "string", "format": "uri", "required": false}
                }
            },
            "tags": ["api", "users", "profile", "v1"]
        }
    ],
    
    "documentation_url": "/docs/memory/profiles/documentation"
}


# =============================================================================
# ALL DEFAULT PROFILES
# =============================================================================

DEFAULT_PROFILES = [
    PROGRAMMING_MEMORY_PROFILE,
    GENERAL_KNOWLEDGE_PROFILE,
    TRAVEL_PLANNING_PROFILE,
    CRM_PROFILE,
    DOCUMENTATION_PROFILE,
]


def get_default_profile(profile_name: str) -> Dict[str, Any]:
    """Get a default profile by name."""
    for profile in DEFAULT_PROFILES:
        if profile["profile_name"] == profile_name:
            return profile
    raise ValueError(f"Unknown default profile: {profile_name}")


def create_system_profiles():
    """
    Create all system profiles in the database.
    This function should be called during app installation or migration.
    """
    import frappe
    
    created = []
    updated = []
    
    for profile_data in DEFAULT_PROFILES:
        profile_name = profile_data["profile_name"]
        
        # Check if profile already exists
        existing = frappe.db.exists("Memory Profile", profile_name)
        
        if existing:
            # Update existing system profile
            doc = frappe.get_doc("Memory Profile", profile_name)
            for key, value in profile_data.items():
                if key != "profile_name":  # Don't update the name
                    setattr(doc, key, value)
            doc.save()
            updated.append(profile_name)
        else:
            # Create new profile
            doc = frappe.get_doc({
                "doctype": "Memory Profile",
                **profile_data
            })
            doc.insert()
            created.append(profile_name)
    
    frappe.db.commit()
    return {"created": created, "updated": updated}
