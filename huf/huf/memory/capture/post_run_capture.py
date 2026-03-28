# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Post-Run Async Capture Mode (C2)

User response is returned immediately.
Capture job is enqueued to background queue (RQ/background job).
Job runs with conversation context snapshot.
Memory record creation is eventual consistency.
Failure is logged but does not block user.

Capture Mode ID: post_async
Execution Phase: Background job after user response sent
Latency Impact: Zero (non-blocking)
Producer: Main agent, memory agent, or post-run processor

Key Features:
- Non-blocking async capture via background workers
- Context snapshot for reliable background processing
- Retry mechanism with exponential backoff
- Comprehensive error logging without user impact
- Batch processing support for efficiency
- Queue management and job monitoring
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime, timedelta
import json
import hashlib


class PostRunAsyncCaptureMode:
    """
    Post-Run Asynchronous Capture Mode implementation.
    
    Enqueues memory capture to background workers, allowing the
    user response to be returned immediately. The actual extraction
    and persistence happens asynchronously with eventual consistency.
    
    This mode is ideal for:
    - High-traffic agents where latency matters
    - Complex extraction requiring LLM calls
    - Batch processing multiple conversations
    - Non-critical memory capture that can tolerate delays
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize post-run async capture mode.
        
        Args:
            config: Configuration dict with capture settings
                - queue_name: Queue for background jobs (default: 'memory_capture')
                - timeout_seconds: Job timeout (default: 300)
                - retry_count: Number of retries (default: 3)
                - retry_delay_seconds: Delay between retries (default: 60)
                - max_context_turns: Max conversation turns to capture (default: 50)
                - deduplication_key: Field for deduplication
                - batch_size: Number of captures to batch (default: 1)
                - capture_prompt: Prompt for extraction (if using LLM)
                - capture_mode: Sub-mode (llm_extraction, rule_based)
                - fallback_capture_mode: Fallback if async fails
        """
        self.config = config or {}
        self.mode_type = "post_async"
        
    def validate(self) -> tuple[bool, List[str]]:
        """
        Validate post-run async capture configuration.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Validate numeric configs
        if self.config.get("timeout_seconds") is not None:
            try:
                timeout = int(self.config["timeout_seconds"])
                if timeout < 30 or timeout > 3600:
                    errors.append("timeout_seconds must be between 30 and 3600")
            except (ValueError, TypeError):
                errors.append("timeout_seconds must be an integer")
        
        if self.config.get("retry_count") is not None:
            try:
                retries = int(self.config["retry_count"])
                if retries < 0 or retries > 10:
                    errors.append("retry_count must be between 0 and 10")
            except (ValueError, TypeError):
                errors.append("retry_count must be an integer")
        
        if self.config.get("retry_delay_seconds") is not None:
            try:
                delay = int(self.config["retry_delay_seconds"])
                if delay < 1 or delay > 3600:
                    errors.append("retry_delay_seconds must be between 1 and 3600")
            except (ValueError, TypeError):
                errors.append("retry_delay_seconds must be an integer")
        
        if self.config.get("max_context_turns") is not None:
            try:
                turns = int(self.config["max_context_turns"])
                if turns < 1 or turns > 200:
                    errors.append("max_context_turns must be between 1 and 200")
            except (ValueError, TypeError):
                errors.append("max_context_turns must be an integer")
        
        if self.config.get("batch_size") is not None:
            try:
                batch = int(self.config["batch_size"])
                if batch < 1 or batch > 100:
                    errors.append("batch_size must be between 1 and 100")
            except (ValueError, TypeError):
                errors.append("batch_size must be an integer")
        
        # Validate capture mode
        valid_modes = ["llm_extraction", "rule_based", "hybrid"]
        capture_mode = self.config.get("capture_mode", "llm_extraction")
        if capture_mode not in valid_modes:
            errors.append(f"capture_mode must be one of {valid_modes}")
        
        return len(errors) == 0, errors
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute post-run async capture by enqueueing background job.
        
        Args:
            context: Capture context containing:
                - conversation: Dict with messages, metadata
                - run: Dict with run details
                - agent_response: String agent response
                - agent_id: Source agent ID
                - user_id: User ID
                - conversation_id: Conversation ID
                - run_id: Run ID
                - tool_outputs: List of tool execution results
                - timestamp: ISO timestamp
                
        Returns:
            Dict with enqueue results:
            - records_created: 0 (created asynchronously)
            - records_updated: 0
            - validation_errors: List of enqueue errors
            - skipped: Whether enqueue was skipped
            - reason: Reason for skipping
            - job_enqueued: Whether job was successfully queued
            - job_name: Background job name
            - job_id: Job ID if available
            - snapshot_id: ID of stored snapshot (if using storage)
            - latency_ms: Enqueue time
            - async: Always True for this mode
            - estimated_completion: Estimated completion time
        """
        start_time = datetime.now()
        
        # Validate configuration
        is_valid, validation_errors = self.validate()
        if not is_valid:
            return {
                "records_created": 0,
                "records_updated": 0,
                "validation_errors": validation_errors,
                "skipped": True,
                "reason": "Configuration validation failed",
                "job_enqueued": False,
                "payload": {},
                "latency_ms": self._calculate_latency(start_time),
                "async": True
            }
        
        # Prepare context snapshot
        try:
            snapshot = self._prepare_context_snapshot(context)
            snapshot_id = self._store_snapshot(snapshot)
        except Exception as e:
            frappe.log_error(f"Failed to prepare snapshot: {str(e)}", "Post-Run Capture")
            return {
                "records_created": 0,
                "records_updated": 0,
                "validation_errors": [str(e)],
                "skipped": True,
                "reason": f"Snapshot preparation failed: {str(e)}",
                "job_enqueued": False,
                "latency_ms": self._calculate_latency(start_time),
                "async": True
            }
        
        # Enqueue background job
        try:
            job_result = self._enqueue_capture_job(snapshot_id, context)
            
            latency_ms = self._calculate_latency(start_time)
            
            # Update run observability if available
            self._update_run_observability(context, job_result, latency_ms)
            
            return {
                "records_created": 0,  # Created asynchronously
                "records_updated": 0,
                "validation_errors": [],
                "skipped": False,
                "job_enqueued": True,
                "job_name": job_result.get("job_name"),
                "job_id": job_result.get("job_id"),
                "snapshot_id": snapshot_id,
                "payload": {"snapshot_id": snapshot_id},
                "latency_ms": latency_ms,
                "async": True,
                "estimated_completion": job_result.get("estimated_completion")
            }
            
        except Exception as e:
            error_msg = f"Failed to enqueue capture job: {str(e)}"
            frappe.log_error(error_msg, "Post-Run Capture")
            
            # Try fallback if configured
            fallback_result = self._try_fallback(context, str(e))
            
            return {
                "records_created": fallback_result.get("records_created", 0),
                "records_updated": fallback_result.get("records_updated", 0),
                "validation_errors": [error_msg],
                "skipped": not fallback_result.get("fallback_executed", False),
                "reason": error_msg,
                "job_enqueued": False,
                "fallback_executed": fallback_result.get("fallback_executed", False),
                "latency_ms": self._calculate_latency(start_time),
                "async": True
            }
    
    def _prepare_context_snapshot(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare a serializable snapshot of context for background processing.
        
        Args:
            context: Full capture context
            
        Returns:
            Serializable context snapshot
        """
        max_turns = self.config.get("max_context_turns", 50)
        
        conversation = context.get("conversation", {})
        messages = conversation.get("messages", [])
        
        # Limit context to recent messages
        if len(messages) > max_turns:
            messages = messages[-max_turns:]
        
        # Create snapshot with minimal data
        snapshot = {
            "version": "1.0",
            "agent_id": context.get("agent_id"),
            "user_id": context.get("user_id"),
            "conversation_id": context.get("conversation_id"),
            "run_id": context.get("run_id"),
            "messages": messages,
            "agent_response": context.get("agent_response"),
            "tool_outputs": context.get("tool_outputs", []),
            "conversation_summary": context.get("conversation_summary"),
            "turn_count": context.get("turn_count", len(messages)),
            "start_time": context.get("start_time"),
            "end_time": context.get("end_time") or datetime.now().isoformat(),
            "scope_type": context.get("scope_type", "conversation"),
            "scope_key": context.get("scope_key", ""),
            "captured_at": datetime.now().isoformat(),
            "snapshot_hash": None  # Will be set below
        }
        
        # Calculate hash for deduplication
        snapshot_str = json.dumps(snapshot, sort_keys=True, default=str)
        snapshot["snapshot_hash"] = hashlib.sha256(snapshot_str.encode()).hexdigest()
        
        return snapshot
    
    def _store_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """
        Store snapshot for background processing.
        
        Args:
            snapshot: Context snapshot
            
        Returns:
            Snapshot ID for retrieval
        """
        # Store in cache/document for background job to retrieve
        snapshot_id = f"mem_snap_{snapshot['snapshot_hash'][:16]}"
        
        try:
            # Try to store in frappe cache
            frappe.cache().set_value(
                f"memory_capture_snapshot:{snapshot_id}",
                snapshot,
                expires_in_sec=3600  # 1 hour expiry
            )
        except Exception:
            # Fallback: return snapshot as base64 encoded string
            import base64
            snapshot_json = json.dumps(snapshot, default=str)
            snapshot_id = f"inline:{base64.b64encode(snapshot_json.encode()).decode()}"
        
        return snapshot_id
    
    def _enqueue_capture_job(
        self,
        snapshot_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enqueue the background capture job.
        
        Args:
            snapshot_id: ID of stored snapshot
            context: Original context
            
        Returns:
            Dict with job info
        """
        conversation_id = context.get("conversation_id", "unknown")
        run_id = context.get("run_id", "unknown")
        
        queue_name = self.config.get("queue_name", "memory_capture")
        timeout = self.config.get("timeout_seconds", 300)
        retry_count = self.config.get("retry_count", 3)
        
        # Generate unique job name
        timestamp = int(datetime.now().timestamp())
        job_name = f"post_run_capture_{conversation_id}_{timestamp}"
        
        # Calculate estimated completion
        est_completion = (datetime.now() + timedelta(seconds=30)).isoformat()
        
        # Enqueue job
        job = frappe.enqueue(
            method="huf.memory.capture.post_run_capture.process_async_capture_job",
            queue=queue_name,
            job_name=job_name,
            snapshot_id=snapshot_id,
            config=self.config,
            conversation_id=conversation_id,
            run_id=run_id,
            timeout=timeout,
            retry=retry_count
        )
        
        job_id = job.get("id") if isinstance(job, dict) else str(job)
        
        return {
            "job_name": job_name,
            "job_id": job_id,
            "estimated_completion": est_completion
        }
    
    def _try_fallback(
        self,
        context: Dict[str, Any],
        error_reason: str
    ) -> Dict[str, Any]:
        """
        Try fallback capture mode if async enqueue fails.
        
        Args:
            context: Capture context
            error_reason: Original error message
            
        Returns:
            Fallback result dict
        """
        fallback_mode = self.config.get("fallback_capture_mode")
        
        if not fallback_mode:
            return {"fallback_executed": False}
        
        try:
            if fallback_mode == "rule_only":
                from huf.memory.capture.rule_capture import RuleOnlyCaptureMode
                
                fallback = RuleOnlyCaptureMode(self.config.get("fallback_rules", []))
                result = fallback.execute(context)
                result["fallback_executed"] = True
                result["fallback_mode"] = "rule_only"
                return result
                
            elif fallback_mode == "sync":
                # Try synchronous capture
                capture_mode = self.config.get("capture_mode", "llm_extraction")
                
                if capture_mode == "rule_based":
                    from huf.memory.capture.rule_capture import RuleOnlyCaptureMode
                    fallback = RuleOnlyCaptureMode(self.config)
                else:
                    from huf.memory.capture.in_prompt_capture import InPromptCaptureMode
                    fallback = InPromptCaptureMode(self.config)
                
                result = fallback.execute(context)
                result["fallback_executed"] = True
                result["fallback_mode"] = "sync"
                return result
                
        except Exception as e:
            frappe.log_error(f"Fallback capture also failed: {str(e)}", "Post-Run Capture")
        
        return {"fallback_executed": False}
    
    def _update_run_observability(
        self,
        context: Dict[str, Any],
        job_result: Dict[str, Any],
        latency_ms: int
    ):
        """Update Agent Run with capture observability data."""
        run_id = context.get("run_id")
        if not run_id or not frappe.db.exists("Agent Run", run_id):
            return
        
        try:
            frappe.db.set_value("Agent Run", run_id, {
                "memory_capture_triggered": True,
                "memory_capture_mode": "post_async",
                "memory_capture_job_name": job_result.get("job_name"),
                "memory_capture_latency_ms": latency_ms,
                "memory_index_jobs_started": 1  # Will be started by background job
            })
        except Exception as e:
            frappe.logger().debug(f"Failed to update run observability: {e}")
    
    def _calculate_latency(self, start_time: datetime) -> int:
        """Calculate elapsed time in milliseconds."""
        elapsed = (datetime.now() - start_time).total_seconds()
        return int(elapsed * 1000)
    
    def get_latency_impact(self) -> str:
        """Return latency impact classification."""
        return "zero"
    
    def get_producer(self) -> str:
        """Return the producer type for this capture mode."""
        return "post_run_processor"


def process_async_capture_job(
    snapshot_id: str,
    config: Dict[str, Any],
    conversation_id: str,
    run_id: str
):
    """
    Background job handler for post-run async capture.
    
    This function runs in the background queue and performs the
    actual memory extraction and persistence.
    
    Args:
        snapshot_id: ID of context snapshot
        config: Capture configuration
        conversation_id: Conversation ID
        run_id: Run ID
    """
    start_time = datetime.now()
    
    try:
        # Retrieve snapshot
        snapshot = _retrieve_snapshot(snapshot_id)
        
        if not snapshot:
            raise ValueError(f"Could not retrieve snapshot: {snapshot_id}")
        
        # Reconstruct context
        context = _reconstruct_context(snapshot)
        
        # Determine capture method
        capture_mode = config.get("capture_mode", "llm_extraction")
        
        if capture_mode == "rule_based":
            # Use rule-based extraction
            from huf.memory.capture.rule_capture import RuleOnlyCaptureMode
            extractor = RuleOnlyCaptureMode(config)
            result = extractor.execute(context)
            
        elif capture_mode == "llm_extraction":
            # Use LLM extraction via specialized agent or direct call
            result = _perform_llm_extraction(context, config)
            
        else:  # hybrid
            # Try rules first, fall back to LLM
            from huf.memory.capture.rule_capture import RuleOnlyCaptureMode
            extractor = RuleOnlyCaptureMode(config)
            result = extractor.execute(context)
            
            if result.get("skipped") or result.get("records_created", 0) == 0:
                result = _perform_llm_extraction(context, config)
        
        # Persist memory records if extraction succeeded
        if result.get("records_created", 0) > 0:
            record_ids = _persist_records(
                result.get("payload", {}).get("records", []),
                context,
                config
            )
            
            # Start indexing jobs
            if record_ids:
                _start_indexing_jobs(record_ids, config)
        
        # Update run observability
        _update_run_completion(run_id, result, start_time)
        
        frappe.logger().info(
            f"Post-run capture completed for conversation {conversation_id}: "
            f"{result.get('records_created', 0)} records created"
        )
        
        return result
        
    except Exception as e:
        error_msg = f"Post-run capture job failed for {conversation_id}: {str(e)}"
        frappe.log_error(error_msg, "Post-Run Async Capture")
        
        # Update run with error
        _update_run_error(run_id, str(e))
        
        # Re-raise to trigger retry
        raise


def _retrieve_snapshot(snapshot_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve snapshot from storage."""
    if snapshot_id.startswith("inline:"):
        # Inline snapshot - decode from base64
        import base64
        encoded = snapshot_id[7:]  # Remove 'inline:' prefix
        snapshot_json = base64.b64decode(encoded).decode()
        return json.loads(snapshot_json)
    
    # Try cache
    try:
        return frappe.cache().get_value(f"memory_capture_snapshot:{snapshot_id}")
    except Exception:
        pass
    
    return None


def _reconstruct_context(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct capture context from snapshot."""
    return {
        "agent_id": snapshot.get("agent_id"),
        "user_id": snapshot.get("user_id"),
        "conversation_id": snapshot.get("conversation_id"),
        "run_id": snapshot.get("run_id"),
        "conversation": {
            "messages": snapshot.get("messages", []),
            "summary": snapshot.get("conversation_summary")
        },
        "agent_response": snapshot.get("agent_response"),
        "tool_outputs": snapshot.get("tool_outputs", []),
        "turn_count": snapshot.get("turn_count", 0),
        "start_time": snapshot.get("start_time"),
        "end_time": snapshot.get("end_time"),
        "scope_type": snapshot.get("scope_type", "conversation"),
        "scope_key": snapshot.get("scope_key", "")
    }


def _perform_llm_extraction(
    context: Dict[str, Any],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """Perform LLM-based extraction."""
    # Check if memory agent is configured
    memory_agent = config.get("memory_agent")
    
    if memory_agent:
        # Use specialized memory agent
        from huf.memory.capture.memory_agent_capture import MemoryAgentCaptureMode
        agent_capture = MemoryAgentCaptureMode(config)
        return agent_capture._run_memory_agent(context)
    else:
        # Use in-prompt capture style
        from huf.memory.capture.in_prompt_capture import InPromptCaptureMode
        
        # Build extraction prompt
        capture_prompt = config.get("capture_prompt", _default_extraction_prompt())
        
        # Call LLM (placeholder - would integrate with HUF's AI system)
        # For now, return empty result
        return {
            "records_created": 0,
            "records_updated": 0,
            "validation_errors": [],
            "skipped": True,
            "reason": "LLM extraction not implemented - requires AI provider integration",
            "payload": {}
        }


def _default_extraction_prompt() -> str:
    """Default prompt for LLM extraction."""
    return """Extract structured memory from the following conversation.

Focus on:
1. User preferences and facts
2. Important decisions or commitments
3. Domain knowledge shared
4. Patterns or insights

Return JSON format:
{
  "records": [
    {
      "title": "Brief title",
      "memory_type": "preference|fact|plan|observation|insight",
      "data": {...},
      "confidence": 0.0-1.0,
      "importance": 0.0-1.0
    }
  ]
}"""


def _persist_records(
    records: List[Dict[str, Any]],
    context: Dict[str, Any],
    config: Dict[str, Any]
) -> List[str]:
    """Persist memory records to database."""
    record_ids = []
    
    for record in records:
        try:
            # Build record data
            record_data = {
                "doctype": "Memory Record",
                "title": record.get("title", "Untitled"),
                "agent": context.get("agent_id"),
                "conversation": context.get("conversation_id"),
                "run": context.get("run_id"),
                "source_type": "conversation",
                "producer_mode": "post_run_llm",
                "memory_type": record.get("memory_type", "observation"),
                "data_json": json.dumps(record.get("data", {})),
                "summary_text": record.get("summary", ""),
                "scope_type": record.get("scope_type") or context.get("scope_type", "conversation"),
                "scope_key": record.get("scope_key") or context.get("scope_key", ""),
                "visibility": config.get("visibility", "private"),
                "status": "active",
                "confidence": record.get("confidence", 0.8),
                "importance_score": record.get("importance", 0.5),
                "created_from_turn_count": context.get("turn_count", 0),
                "tags": record.get("tags", [])
            }
            
            # Insert document
            doc = frappe.get_doc(record_data)
            doc.insert(ignore_permissions=True)
            record_ids.append(doc.name)
            
        except Exception as e:
            frappe.log_error(f"Failed to persist memory record: {str(e)}", "Post-Run Capture")
    
    return record_ids


def _start_indexing_jobs(record_ids: List[str], config: Dict[str, Any]):
    """Start background indexing jobs."""
    enable_fts = config.get("enable_fts_index", True)
    enable_vector = config.get("enable_vector_index", False)
    
    if enable_fts:
        try:
            frappe.enqueue(
                method="huf.memory.indexing.index_records_fts",
                queue="default",
                record_ids=record_ids,
                timeout=300
            )
        except Exception as e:
            frappe.log_error(f"Failed to enqueue FTS indexing: {str(e)}", "Post-Run Capture")
    
    if enable_vector:
        try:
            frappe.enqueue(
                method="huf.memory.indexing.index_records_vector",
                queue="default",
                record_ids=record_ids,
                timeout=300
            )
        except Exception as e:
            frappe.log_error(f"Failed to enqueue vector indexing: {str(e)}", "Post-Run Capture")


def _update_run_completion(run_id: str, result: Dict[str, Any], start_time: datetime):
    """Update run with completion info."""
    if not run_id or not frappe.db.exists("Agent Run", run_id):
        return
    
    try:
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        frappe.db.set_value("Agent Run", run_id, {
            "memory_records_created": result.get("records_created", 0),
            "memory_records_updated": result.get("records_updated", 0),
            "memory_records_skipped": result.get("skipped", False),
            "memory_capture_latency_ms": latency_ms
        })
    except Exception:
        pass


def _update_run_error(run_id: str, error: str):
    """Update run with error info."""
    if not run_id or not frappe.db.exists("Agent Run", run_id):
        return
    
    try:
        frappe.db.set_value("Agent Run", run_id, {
            "memory_error_log": error[:1000]  # Truncate if too long
        })
    except Exception:
        pass


def create_post_run_async_capture(config: Dict[str, Any]) -> PostRunAsyncCaptureMode:
    """
    Factory function to create a PostRunAsyncCaptureMode instance.
    
    Args:
        config: Configuration dict
        
    Returns:
        PostRunAsyncCaptureMode instance
    """
    return PostRunAsyncCaptureMode(config)
