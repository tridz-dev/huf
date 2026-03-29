"""Agent Integration Memory Patch

This file shows the exact changes needed in huf/ai/agent_integration.py
to integrate the memory system with the agent runner.

Apply these changes to wire memory capture and retrieval into agent execution.
"""

# =============================================================================
# CHANGE 1: Add import at the top of agent_integration.py
# =============================================================================
# Add after existing imports (around line 15):

from huf.memory.runner_hooks import pre_run_hook, post_run_hook, should_enable_memory


# =============================================================================
# CHANGE 2: Inject memory context before agent run
# =============================================================================
# In run_agent_sync(), after knowledge context injection (around line 750),
# add the following code before calling RunProvider.run():

# Find this section in agent_integration.py (around line 750-800):
#         # Inject knowledge context if available
#         if knowledge_context and knowledge_context.get("context_text"):
#             enhanced_prompt = inject_knowledge_context(base_prompt, knowledge_context)
#             ...
#         else:
#             enhanced_prompt = base_prompt

# AFTER THAT BLOCK, ADD:

        # =========================================================================
        # MEMORY SYSTEM INJECTION
        # =========================================================================
        # Inject memory context before agent execution
        if should_enable_memory(agent_doc):
            try:
                enhanced_prompt = pre_run_hook(
                    agent_doc=agent_doc,
                    prompt=enhanced_prompt,
                    conversation=conversation,
                    user_id=frappe.session.user
                )
            except Exception as e:
                frappe.log_error(f"Memory injection failed: {e}", "Agent Memory")
        # =========================================================================


# =============================================================================
# CHANGE 3: Capture memory after successful agent run
# =============================================================================
# In run_agent_sync(), after setting run status to Success (around line 950),
# add the following code before returning the result:

# Find this section in agent_integration.py (around line 950):
#         frappe.db.set_value("Agent Run", run_doc.name, {
#             "status": "Success",
#             "response": final_output,
#             "prompt": prompt,
#             "model": resolved_model,
#             "provider": resolved_provider,
#             "end_time": now_datetime()
#         }, update_modified=True)
#         safe_commit()

# AFTER safe_commit(), ADD:

        # =========================================================================
        # MEMORY SYSTEM CAPTURE
        # =========================================================================
        # Capture memories from this run
        if should_enable_memory(agent_doc):
            try:
                post_run_hook(
                    agent_doc=agent_doc,
                    run_doc=run_doc,
                    conversation=conversation,
                    agent_response=final_output,
                    conversation_history=history,
                    tool_outputs=[]  # TODO: Pass actual tool outputs from execution
                )
            except Exception as e:
                frappe.log_error(f"Memory capture failed: {e}", "Agent Memory")
        # =========================================================================


# =============================================================================
# CHANGE 4: Same changes for run_agent_stream()
# =============================================================================
# In run_agent_stream(), make the same two changes:
# 1. After knowledge context injection, add pre_run_hook() call
# 2. After successful completion, add post_run_hook() call

# The stream function follows similar patterns to run_agent_sync.


# =============================================================================
# ALTERNATIVE: Minimal Integration (Fewer Lines Changed)
# =============================================================================
# If you prefer a minimal integration that only touches a few lines:

# 1. At the top, add:
from huf.memory.integration import inject_memory_into_prompt, capture_memory_after_run

# 2. After knowledge injection (around line 780):
if getattr(agent_doc, 'enable_memory', False) or getattr(agent_doc, 'memory_policy', None):
    enhanced_prompt = inject_memory_into_prompt(
        prompt=enhanced_prompt,
        agent_name=agent_doc.name,
        conversation_id=conversation.name
    )

# 3. After success (around line 955):
if getattr(agent_doc, 'enable_memory', False) or getattr(agent_doc, 'memory_policy', None):
    capture_memory_after_run(
        agent_name=agent_doc.name,
        run_id=run_doc.name,
        conversation_id=conversation.name,
        agent_response=final_output,
        conversation_history=history
    )
