"""
HUF Memory System - Setup and Data Seeding

This module handles the installation and migration of the Memory System,
including seeding default profiles and policies.
"""

import frappe
from frappe import _

# Default Memory Profiles
DEFAULT_PROFILES = [
    {
        "profile_name": "Programming",
        "description": "Optimized for software development tasks, code reviews, debugging, and technical discussions. Captures code patterns, architectural decisions, and developer preferences.",
        "category": "programming",
        "is_system_profile": 1,
        "default_schema_json": {
            "type": "object",
            "properties": {
                "code_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Reusable code patterns or idioms"
                },
                "tech_stack": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Technologies, frameworks, and languages"
                },
                "coding_preferences": {
                    "type": "object",
                    "description": "Style preferences and conventions"
                },
                "debugging_context": {
                    "type": "object",
                    "description": "Ongoing debugging sessions or issues"
                },
                "architectural_decisions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key architectural choices and rationale"
                }
            }
        },
        "default_capture_prompt": """Extract programming-related memories from this conversation. Focus on:
1. Code patterns, algorithms, or solutions discussed
2. Technology preferences and constraints
3. Architectural decisions and their rationale
4. Debugging approaches that worked
5. Development workflows and preferences

Format as structured JSON with appropriate fields.""",
        "default_capture_stage": "post_response_async",
        "default_frequency": "every_n_turns",
        "default_scope_type": "conversation",
        "default_indexing_mode": "both",
        "default_retrieval_mode": "hybrid",
        "default_memory_type_mapping": {
            "code": "domain_object",
            "bug": "observation",
            "pattern": "insight",
            "preference": "preference",
            "architecture": "fact"
        },
        "recommended_model": "gpt-4o",
        "recommended_provider": "OpenAI"
    },
    {
        "profile_name": "General Knowledge",
        "description": "General-purpose profile for everyday conversations, fact collection, and knowledge management. Suitable for personal assistants and general chat.",
        "category": "general",
        "is_system_profile": 1,
        "default_schema_json": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "predicate": {"type": "string"},
                            "confidence": {"type": "number"}
                        }
                    },
                    "description": "Factual information extracted"
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Topics discussed"
                },
                "interests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "User interests discovered"
                },
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Questions asked by user"
                }
            }
        },
        "default_capture_prompt": """Extract key information from this conversation. Capture:
1. Important facts mentioned
2. Topics of interest to the user
3. Questions that were asked
4. Preferences expressed
5. Any commitments or follow-ups

Organize the information clearly and concisely.""",
        "default_capture_stage": "conversation_end",
        "default_frequency": "conversation_end",
        "default_scope_type": "user",
        "default_indexing_mode": "both",
        "default_retrieval_mode": "inject",
        "default_memory_type_mapping": {
            "fact": "fact",
            "preference": "preference",
            "interest": "profile",
            "question": "observation"
        },
        "recommended_model": "gpt-4o-mini",
        "recommended_provider": "OpenAI"
    },
    {
        "profile_name": "Travel Planning",
        "description": "Specialized for travel discussions, itinerary planning, destination research, and travel preferences. Captures destinations, dates, preferences, and booking details.",
        "category": "travel",
        "is_system_profile": 1,
        "default_schema_json": {
            "type": "object",
            "properties": {
                "destinations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Places being considered or visited"
                },
                "dates": {
                    "type": "object",
                    "properties": {
                        "departure": {"type": "string", "format": "date"},
                        "return": {"type": "string", "format": "date"},
                        "flexibility": {"type": "string"}
                    }
                },
                "travelers": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "composition": {"type": "string"},
                        "special_requirements": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "preferences": {
                    "type": "object",
                    "properties": {
                        "accommodation": {"type": "string"},
                        "activities": {"type": "array", "items": {"type": "string"}},
                        "budget_range": {"type": "string"},
                        "dietary": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "bookings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["flight", "hotel", "activity", "transport"]},
                            "details": {"type": "object"},
                            "confirmation": {"type": "string"}
                        }
                    }
                }
            }
        },
        "default_capture_prompt": """Extract travel-related information from this conversation. Capture:
1. Destinations mentioned (cities, countries, attractions)
2. Travel dates and flexibility
3. Number and type of travelers
4. Accommodation preferences (hotel type, location, amenities)
5. Activity interests and preferences
6. Budget considerations
7. Any bookings made or confirmed
8. Special requirements (dietary, accessibility, etc.)

Structure as detailed travel itinerary data.""",
        "default_capture_stage": "post_response_async",
        "default_frequency": "every_n_turns",
        "default_scope_type": "user",
        "default_indexing_mode": "both",
        "default_retrieval_mode": "hybrid",
        "default_memory_type_mapping": {
            "destination": "domain_object",
            "booking": "fact",
            "preference": "preference",
            "date": "observation"
        },
        "recommended_model": "gpt-4o",
        "recommended_provider": "OpenAI"
    },
    {
        "profile_name": "Documentation",
        "description": "Optimized for technical documentation, knowledge base articles, and reference material. Captures structured documentation with versioning and cross-references.",
        "category": "documentation",
        "is_system_profile": 1,
        "default_schema_json": {
            "type": "object",
            "properties": {
                "document_type": {
                    "type": "string",
                    "enum": ["api_reference", "tutorial", "guide", "faq", "changelog", "concept"]
                },
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"},
                            "code_examples": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                },
                "related_topics": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "version": {"type": "string"},
                "last_updated": {"type": "string", "format": "date-time"}
            }
        },
        "default_capture_prompt": """Extract documentation content from this conversation. Structure as:
1. Document type (API reference, tutorial, guide, etc.)
2. Clear title and summary
3. Organized sections with headings
4. Code examples where applicable
5. Related topics for cross-referencing
6. Version information if mentioned

Format as structured documentation suitable for a knowledge base.""",
        "default_capture_stage": "post_response_async",
        "default_frequency": "every_n_turns",
        "default_scope_type": "namespace",
        "default_indexing_mode": "both",
        "default_retrieval_mode": "hybrid",
        "default_memory_type_mapping": {
            "documentation": "domain_object",
            "api": "fact",
            "tutorial": "insight",
            "concept": "fact"
        },
        "recommended_model": "gpt-4o",
        "recommended_provider": "OpenAI"
    },
    {
        "profile_name": "Science/Research",
        "description": "Designed for scientific discussions, research analysis, and academic work. Captures hypotheses, experimental data, citations, and research findings with proper attribution.",
        "category": "science",
        "is_system_profile": 1,
        "default_schema_json": {
            "type": "object",
            "properties": {
                "research_topic": {"type": "string"},
                "hypothesis": {"type": "string"},
                "methodology": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "data_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metric": {"type": "string"},
                            "value": {"type": "string"},
                            "unit": {"type": "string"},
                            "uncertainty": {"type": "string"}
                        }
                    }
                },
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "authors": {"type": "string"},
                            "title": {"type": "string"},
                            "year": {"type": "integer"},
                            "doi": {"type": "string"}
                        }
                    }
                },
                "conclusions": {"type": "string"},
                "future_work": {"type": "array", "items": {"type": "string"}}
            }
        },
        "default_capture_prompt": """Extract research and scientific content from this conversation. Capture:
1. Research topics and questions
2. Hypotheses being tested
3. Methodologies described
4. Key findings and results
5. Quantitative data with units
6. Citations and references
7. Conclusions drawn
8. Future research directions

Maintain scientific rigor and preserve uncertainty/qualifications.""",
        "default_capture_stage": "post_response_async",
        "default_frequency": "conversation_end",
        "default_scope_type": "namespace",
        "default_indexing_mode": "both",
        "default_retrieval_mode": "hybrid",
        "default_memory_type_mapping": {
            "hypothesis": "insight",
            "finding": "fact",
            "data": "domain_object",
            "citation": "fact",
            "method": "insight"
        },
        "recommended_model": "gpt-4o",
        "recommended_provider": "OpenAI"
    },
    {
        "profile_name": "Language Learning",
        "description": "Optimized for language learning conversations, vocabulary acquisition, grammar explanations, and progress tracking. Captures new words, phrases, mistakes, and learning milestones.",
        "category": "language",
        "is_system_profile": 1,
        "default_schema_json": {
            "type": "object",
            "properties": {
                "target_language": {"type": "string"},
                "native_language": {"type": "string"},
                "proficiency_level": {
                    "type": "string",
                    "enum": ["beginner", "elementary", "intermediate", "upper_intermediate", "advanced", "proficient"]
                },
                "vocabulary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "word": {"type": "string"},
                            "translation": {"type": "string"},
                            "context": {"type": "string"},
                            "part_of_speech": {"type": "string"}
                        }
                    }
                },
                "phrases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "phrase": {"type": "string"},
                            "meaning": {"type": "string"},
                            "usage_context": {"type": "string"}
                        }
                    }
                },
                "grammar_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "rule": {"type": "string"},
                            "explanation": {"type": "string"},
                            "examples": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                },
                "mistakes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string"},
                            "correction": {"type": "string"},
                            "explanation": {"type": "string"}
                        }
                    }
                },
                "learning_goals": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        },
        "default_capture_prompt": """Extract language learning content from this conversation. Capture:
1. New vocabulary words with translations and context
2. Useful phrases and expressions
3. Grammar rules explained
4. Mistakes made and their corrections
5. Learning goals and objectives
6. Progress indicators

Include both the target language and native language equivalents.""",
        "default_capture_stage": "post_response_async",
        "default_frequency": "every_n_turns",
        "default_scope_type": "user",
        "default_indexing_mode": "both",
        "default_retrieval_mode": "hybrid",
        "default_memory_type_mapping": {
            "vocabulary": "domain_object",
            "grammar": "insight",
            "mistake": "observation",
            "goal": "plan"
        },
        "recommended_model": "gpt-4o",
        "recommended_provider": "OpenAI"
    },
    {
        "profile_name": "CRM",
        "description": "Customer Relationship Management profile for sales, support, and client interactions. Captures contact details, interaction history, preferences, and deal/opportunity information.",
        "category": "crm",
        "is_system_profile": 1,
        "default_schema_json": {
            "type": "object",
            "properties": {
                "contact": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                        "phone": {"type": "string"},
                        "company": {"type": "string"},
                        "title": {"type": "string"}
                    }
                },
                "interaction_type": {
                    "type": "string",
                    "enum": ["call", "email", "meeting", "demo", "support", "follow_up"]
                },
                "opportunity": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "number"},
                        "currency": {"type": "string"},
                        "stage": {"type": "string"},
                        "probability": {"type": "number"},
                        "expected_close": {"type": "string", "format": "date"}
                    }
                },
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "pain_points": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "next_steps": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "follow_up_date": {"type": "string", "format": "date"},
                "sentiment": {
                    "type": "string",
                    "enum": ["very_positive", "positive", "neutral", "negative", "very_negative"]
                }
            }
        },
        "default_capture_prompt": """Extract CRM information from this conversation. Capture:
1. Contact details (name, email, phone, company, title)
2. Type of interaction (call, email, meeting, demo, support)
3. Opportunity/deal information
4. Key discussion points
5. Customer pain points or needs
6. Agreed next steps and follow-up dates
7. Overall sentiment of the interaction

Structure as actionable CRM data for sales/support workflows.""",
        "default_capture_stage": "conversation_end",
        "default_frequency": "conversation_end",
        "default_scope_type": "namespace",
        "default_indexing_mode": "both",
        "default_retrieval_mode": "inject",
        "default_memory_type_mapping": {
            "contact": "profile",
            "opportunity": "domain_object",
            "interaction": "observation",
            "follow_up": "plan"
        },
        "recommended_model": "gpt-4o",
        "recommended_provider": "OpenAI"
    }
]

# Default Memory Policy Templates
DEFAULT_POLICIES = [
    {
        "policy_name": "Default Conservative",
        "description": "Conservative memory capture with high confidence threshold. Good for production environments where memory quality is critical.",
        "enabled": 1,
        "capture_owner": "post_run_llm",
        "capture_stage": "post_response_async",
        "capture_frequency_type": "conversation_end",
        "conversation_end_strategy": "idle_timeout",
        "idle_timeout_minutes": 30,
        "allow_open_schema": 0,
        "require_json_schema_match": 1,
        "allow_update_existing": 1,
        "allow_merge": 1,
        "allow_append": 0,
        "min_confidence": 0.8,
        "store_raw_payload": 0,
        "store_summary": 1,
        "enable_fts_index": 1,
        "enable_vector_index": 1,
        "retrieval_mode_default": "hybrid",
        "max_items_to_inject": 5,
        "max_tokens_to_inject": 1500
    },
    {
        "policy_name": "Default Aggressive",
        "description": "Aggressive memory capture with lower confidence threshold. Captures more memories but may include lower quality entries. Good for development and experimentation.",
        "enabled": 1,
        "capture_owner": "main_agent",
        "capture_stage": "in_prompt",
        "capture_frequency_type": "every_run",
        "allow_open_schema": 1,
        "require_json_schema_match": 0,
        "allow_update_existing": 1,
        "allow_merge": 1,
        "allow_append": 1,
        "min_confidence": 0.5,
        "store_raw_payload": 1,
        "store_summary": 1,
        "enable_fts_index": 1,
        "enable_vector_index": 1,
        "retrieval_mode_default": "inject",
        "max_items_to_inject": 10,
        "max_tokens_to_inject": 3000
    },
    {
        "policy_name": "Default Rules-Only",
        "description": "Memory capture using only rule-based extraction, no LLM involvement. Fast and deterministic but less flexible.",
        "enabled": 1,
        "capture_owner": "rules_only",
        "capture_stage": "post_response_sync",
        "capture_frequency_type": "every_n_turns",
        "allow_open_schema": 0,
        "require_json_schema_match": 1,
        "allow_update_existing": 1,
        "allow_merge": 0,
        "allow_append": 0,
        "min_confidence": 0.9,
        "store_raw_payload": 0,
        "store_summary": 0,
        "enable_fts_index": 1,
        "enable_vector_index": 0,
        "retrieval_mode_default": "tool_only",
        "max_items_to_inject": 3,
        "max_tokens_to_inject": 1000
    }
]


def after_install():
    """Called after app installation. Seeds default data."""
    frappe.db.commit()
    seed_memory_profiles()
    seed_memory_policies()
    frappe.db.commit()


def after_migrate():
    """Called after migration. Ensures default data exists (idempotent)."""
    seed_memory_profiles()
    seed_memory_policies()
    frappe.db.commit()


def seed_memory_profiles():
    """Seed default memory profiles if they don't exist."""
    for profile_data in DEFAULT_PROFILES:
        try:
            # Check if profile already exists
            existing = frappe.db.exists("Memory Profile", {"profile_name": profile_data["profile_name"]})
            
            if existing:
                # Update system profiles to ensure they have latest defaults
                if profile_data.get("is_system_profile"):
                    doc = frappe.get_doc("Memory Profile", existing)
                    # Only update description and schema if not modified by user
                    if not doc.modified_by or doc.modified_by == "Administrator":
                        doc.description = profile_data["description"]
                        doc.default_schema_json = frappe.as_json(profile_data["default_schema_json"])
                        doc.default_capture_prompt = profile_data["default_capture_prompt"]
                        doc.save(ignore_permissions=True)
                        frappe.logger().info(f"Updated system Memory Profile: {profile_data['profile_name']}")
                continue
            
            # Create new profile
            doc = frappe.new_doc("Memory Profile")
            doc.update(profile_data)
            doc.insert(ignore_permissions=True)
            frappe.logger().info(f"Created Memory Profile: {profile_data['profile_name']}")
            
        except Exception as e:
            frappe.logger().error(f"Failed to seed Memory Profile '{profile_data['profile_name']}': {str(e)}")
            # Don't raise - allow other profiles to be created


def seed_memory_policies():
    """Seed default memory policies if they don't exist."""
    for policy_data in DEFAULT_POLICIES:
        try:
            # Check if policy already exists
            existing = frappe.db.exists("Memory Policy", {"policy_name": policy_data["policy_name"]})
            
            if existing:
                continue  # Don't modify existing policies
            
            # Create new policy
            doc = frappe.new_doc("Memory Policy")
            doc.update(policy_data)
            doc.insert(ignore_permissions=True)
            frappe.logger().info(f"Created Memory Policy: {policy_data['policy_name']}")
            
        except Exception as e:
            frappe.logger().error(f"Failed to seed Memory Policy '{policy_data['policy_name']}': {str(e)}")
            # Don't raise - allow other policies to be created


def get_default_profile(profile_name: str) -> dict:
    """Get a default profile by name."""
    for profile in DEFAULT_PROFILES:
        if profile["profile_name"] == profile_name:
            return profile
    return {}


def get_default_policy(policy_name: str) -> dict:
    """Get a default policy by name."""
    for policy in DEFAULT_POLICIES:
        if policy["policy_name"] == policy_name:
            return policy
    return {}


def reset_system_profiles():
    """Reset all system profiles to their default values. Use with caution."""
    for profile_data in DEFAULT_PROFILES:
        if not profile_data.get("is_system_profile"):
            continue
            
        try:
            existing = frappe.db.exists("Memory Profile", {"profile_name": profile_data["profile_name"]})
            
            if existing:
                doc = frappe.get_doc("Memory Profile", existing)
                doc.update(profile_data)
                doc.save(ignore_permissions=True)
                frappe.logger().info(f"Reset system Memory Profile: {profile_data['profile_name']}")
            else:
                doc = frappe.new_doc("Memory Profile")
                doc.update(profile_data)
                doc.insert(ignore_permissions=True)
                frappe.logger().info(f"Created system Memory Profile: {profile_data['profile_name']}")
                
        except Exception as e:
            frappe.logger().error(f"Failed to reset Memory Profile '{profile_data['profile_name']}': {str(e)}")


def get_seeding_stats() -> dict:
    """Get statistics about seeded data."""
    return {
        "profiles": {
            "total_default": len(DEFAULT_PROFILES),
            "created": frappe.db.count("Memory Profile", {"is_system_profile": 1}),
            "available": [p["profile_name"] for p in DEFAULT_PROFILES]
        },
        "policies": {
            "total_default": len(DEFAULT_POLICIES),
            "created": frappe.db.count("Memory Policy"),
            "available": [p["policy_name"] for p in DEFAULT_POLICIES]
        }
    }