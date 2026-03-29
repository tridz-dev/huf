# Best Practices

Recommendations for using the HUF Memory System in production.

## Table of Contents

1. [Security](#security)
2. [Performance](#performance)
3. [Data Quality](#data-quality)
4. [User Privacy](#user-privacy)
5. [Scaling](#scaling)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)

---

## Security

### Scope Isolation

Always use the narrowest scope that meets your needs:

```python
# GOOD: User scope for personal data
scope_type = "user"
scope_key = user_id

# BAD: Global scope for personal preferences
scope_type = "global"  # Don't do this!
```

### Sensitive Data

Be cautious about what gets captured:

```python
# Filter sensitive data before capture
def sanitize_for_memory(raw_text):
    # Remove PII
    text = remove_email_addresses(raw_text)
    text = remove_phone_numbers(text)
    text = remove_credit_cards(text)
    
    # Remove secrets
    text = remove_api_keys(text)
    text = remove_passwords(text)
    
    return text
```

### Access Control

Review permissions regularly:

```python
# Check who can access memories
frappe.get_all("DocPerm", 
    filters={"parent": "Memory Record"},
    fields=["role", "read", "write", "create", "delete"]
)
```

### Audit Trail

Enable change tracking:

```python
# Memory Record DocType has track_changes = 1
# Review changes periodically
changes = frappe.get_all("Version",
    filters={"ref_doctype": "Memory Record"},
    fields=["docname", "data", "modified_by", "modified"]
)
```

---

## Performance

### Indexing Strategy

Choose indexes based on your query patterns:

| Query Pattern | Recommended Index |
|---------------|-------------------|
| Keyword search | FTS only |
| Natural language | Vector only |
| Mixed queries | Hybrid (both) |
| ID lookups | None needed |

### Batch Operations

For bulk operations, use batching:

```python
# BAD: One by one
for memory in memories:
    create_memory(**memory)

# GOOD: Batch insert
from huf.huf.memory.storage import batch_create_memories

batch_create_memories(memories, batch_size=100)
```

### Lazy Indexing

Index in background to avoid blocking:

```python
# Schedule indexing as background job
frappe.enqueue(
    "huf.huf.memory.indexing.index_memory",
    memory_id=memory.name,
    queue="long"
)
```

### Caching

Cache frequently accessed memories:

```python
from frappe.utils.redis_wrapper import RedisWrapper

redis = RedisWrapper()
cache_key = f"memory_context:{user_id}"

# Try cache first
context = redis.get_value(cache_key)
if not context:
    context = get_memory_context(...)
    redis.set_value(cache_key, context, expires_in_sec=300)
```

### Connection Pooling

Use connection pooling for vector databases:

```python
# In your configuration
vector_db_config = {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30
}
```

---

## Data Quality

### Validation

Always validate captured data:

```python
# Use JSON Schema validation
policy.require_json_schema_match = True
policy.capture_schema_json = {
    "type": "object",
    "required": ["customer_id"],
    "properties": {
        "customer_id": {"type": "string"},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]}
    }
}
```

### Confidence Thresholds

Set appropriate confidence levels:

```python
# Conservative (high quality, fewer memories)
policy.min_confidence = 0.8

# Balanced (recommended for most cases)
policy.min_confidence = 0.7

# Aggressive (more memories, may include noise)
policy.min_confidence = 0.5
```

### Deduplication

Enable deduplication to prevent duplicates:

```python
policy.allow_update_existing = True
policy.allow_merge = True
```

### Regular Cleanup

Schedule cleanup of old/expired memories:

```python
# Run daily cleanup
frappe.enqueue(
    "huf.huf.memory.maintenance.cleanup_expired_memories",
    queue="long"
)

# Archive old memories
frappe.enqueue(
    "huf.huf.memory.maintenance.archive_old_memories",
    days=90,
    queue="long"
)
```

---

## User Privacy

### Consent

Implement user consent for memory capture:

```python
def should_capture_memory(user_id):
    # Check user preference
    user_prefs = get_user_preferences(user_id)
    return user_prefs.get("allow_memory_capture", True)

# In capture pipeline
if not should_capture_memory(user_id):
    return {"success": False, "reason": "user_opted_out"}
```

### Right to Deletion

Honor deletion requests promptly:

```python
def delete_user_memories(user_id):
    """Delete all memories for a user (GDPR compliance)"""
    memories = frappe.get_all("Memory Record",
        filters={"scope_type": "user", "scope_key": user_id}
    )
    
    for memory in memories:
        frappe.delete_doc("Memory Record", memory.name)
```

### Data Retention

Set appropriate retention periods:

```python
# Auto-expire old memories
memory.ttl_days = 365  # 1 year for most memories
memory.effective_until = calculate_expiration(memory.created_at)
```

### Encryption

Consider encrypting sensitive memory data:

```python
from frappe.utils.password import encrypt

# Encrypt before storage
if memory_contains_sensitive_data(memory):
    memory.data_json = encrypt(json.dumps(memory.data))
```

---

## Scaling

### Horizontal Scaling

For high-traffic deployments:

1. **Separate indexing service**: Run vector indexing on dedicated nodes
2. **Read replicas**: Use database replicas for search queries
3. **Cache layer**: Redis for frequently accessed memories
4. **CDN**: Serve static memory assets via CDN

### Sharding

Shard memories by scope for better performance:

```python
# Shard key based on user_id
shard_id = hash(user_id) % num_shards
shard_table = f"tabMemory Record_{shard_id}"
```

### Async Processing

Use queues for heavy operations:

```python
# Capture in background
frappe.enqueue(
    "huf.huf.memory.capture.capture_memory_async",
    conversation_id=conversation_id,
    queue="default"
)
```

### Database Optimization

Regular database maintenance:

```sql
-- Optimize FTS index
OPTIMIZE TABLE tabMemory Record;

-- Rebuild vector index
-- (Implementation depends on backend)

-- Analyze table for query planner
ANALYZE TABLE tabMemory Record;
```

---

## Monitoring

### Key Metrics

Track these metrics:

```python
METRICS = {
    "memory_capture_rate": "Memories created per hour",
    "capture_success_rate": "Successful captures / Total attempts",
    "search_latency_p99": "99th percentile search latency",
    "index_build_time": "Time to build/rebuild indexes",
    "storage_size": "Total memory storage size",
    "retrieval_hit_rate": "Memories found / Searches",
    "user_satisfaction": "Feedback scores on memory relevance"
}
```

### Health Checks

Implement health check endpoints:

```python
@frappe.whitelist()
def memory_health_check():
    checks = {
        "database": check_database_connection(),
        "fts_index": check_fts_index_health(),
        "vector_index": check_vector_index_health(),
        "queue": check_queue_depth(),
        "storage": check_storage_capacity()
    }
    
    all_healthy = all(checks.values())
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": checks
    }
```

### Alerting

Set up alerts for issues:

```python
ALERTS = [
    {
        "condition": "capture_success_rate < 0.9",
        "severity": "warning",
        "message": "Memory capture success rate below 90%"
    },
    {
        "condition": "search_latency_p99 > 1000ms",
        "severity": "critical",
        "message": "Search latency critically high"
    },
    {
        "condition": "storage_size > 100GB",
        "severity": "warning",
        "message": "Memory storage approaching limit"
    }
]
```

### Logging

Use structured logging:

```python
import logging

logger = logging.getLogger("huf.memory")

logger.info("Memory captured", extra={
    "memory_id": memory.name,
    "agent": memory.agent,
    "type": memory.memory_type,
    "confidence": memory.confidence,
    "duration_ms": capture_duration
})
```

---

## Troubleshooting

### Common Issues

#### High Memory Usage

**Symptoms**: Server running out of memory

**Solutions**:
1. Reduce `max_items_to_inject`
2. Lower `max_tokens_to_inject`
3. Use streaming for large result sets
4. Implement pagination

#### Slow Searches

**Symptoms**: Search taking > 1 second

**Solutions**:
1. Add more specific filters
2. Use FTS only instead of hybrid
3. Increase database connection pool
4. Add caching layer
5. Consider read replicas

#### Missing Memories

**Symptoms**: Expected memories not found

**Checks**:
1. Verify memory status is "active"
2. Check scope matches query
3. Confirm indexing is complete
4. Review confidence threshold
5. Check temporal filters

#### Duplicate Memories

**Symptoms**: Multiple similar memories created

**Solutions**:
1. Enable `allow_update_existing`
2. Increase similarity threshold
3. Implement content hashing
4. Use stricter capture frequency

### Debug Mode

Enable debug logging:

```python
# In site_config.json
{
    "logging": {
        "huf.memory": "DEBUG"
    }
}
```

### Diagnostic Commands

```bash
# Check memory counts
bench --site site.com console
frappe.db.count("Memory Record")

# Verify indexes
frappe.db.sql("""
    SELECT name, fts_indexed, vector_indexed 
    FROM `tabMemory Record` 
    WHERE fts_indexed = 0 AND vector_indexed = 0
    LIMIT 10
""")

# Check policy usage
frappe.get_all("Memory Record", 
    fields=["memory_profile", "COUNT(*) as count"],
    group_by="memory_profile"
)
```

---

## Production Checklist

Before deploying to production:

- [ ] Security review completed
- [ ] Scope configuration verified
- [ ] Indexes built and tested
- [ ] Backup strategy in place
- [ ] Monitoring configured
- [ ] Alerts set up
- [ ] Rate limiting enabled
- [ ] Error handling tested
- [ ] Performance benchmarks met
- [ ] Documentation updated
- [ ] Runbook created
- [ ] GDPR/privacy compliance verified

---

## Additional Resources

- [Overview](./overview.md) - Architecture and concepts
- [Getting Started](./getting-started.md) - Quick setup guide
- [Profiles](./profiles.md) - Profile documentation
- [Capture Modes](./capture-modes.md) - Capture configuration
- [Retrieval](./retrieval.md) - Search and injection
- [API Reference](./api-reference.md) - Complete API docs