# P0 Fix Audit Report

**Scope:** P0 items from `DEEP_DIVE2.md` only.
**Branches:**
- `fix/p0-bare-except`
- `fix/p0-swallow-commit-hazards`
**Baseline tag:** `pre-p0-fix`

This report documents the before/after state of every site changed by the P0 implementation plan.

---

## Evidence: bare `except:` count

```bash
rg -n "except:\s*$" huf/ai --type py
```

Output:

```
No bare except blocks found
```

---

## Batch 1 — Bare `except:` (4 sites)

All four sites now catch `json.JSONDecodeError`, `TypeError`, and `KeyError`, log a `frappe.logger("huf").warning()`, and continue without the memory snapshot. Happy path is unchanged.

### 1. `ai/agent_integration.py:853` — `run_agent_stream`

**Before:**

```python
             try:
                data_snapshot = json.loads(conversation.conversation_data)
                ...
             except:
                 pass
```

**After:**

```python
             except (json.JSONDecodeError, TypeError, KeyError) as e:
                 frappe.logger("huf").warning(
                     f"Skipped conversation_data memory snapshot for conversation "
                     f"{conversation.name}: {e}"
                 )
```

**Test:** `huf.ai.tests.test_p0_bare_except.TestConversationDataLoadState`

---

### 2. `ai/agent_integration.py:1515` — `run_agent_sync`

**Before:**

```python
             try:
                data_snapshot = json.loads(conversation.conversation_data)
                ...
             except:
                 pass
```

**After:** same pattern as site 1.

**Test:** `huf.ai.tests.test_p0_bare_except.TestConversationDataLoadState`

---

### 3. `ai/sdk_tools.py:1250` — `_load_state` double-decode

**Before:**

```python
            if isinstance(data, str): # Handle double encoded
                try: data = json.loads(data)
                except: pass
```

**After:**

```python
            if isinstance(data, str): # Handle double encoded
                try: data = json.loads(data)
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    frappe.logger("huf").warning(
                        f"Skipped double-decoding of conversation_data state: {e}"
                    )
```

**Test:** `huf.ai.tests.test_p0_bare_except.TestConversationDataLoadState`

---

### 4. `ai/conversation_data_tools.py:24` — `_load_state` double-decode

Same pattern as site 3.

**Test:** `huf.ai.tests.test_p0_bare_except.TestConversationDataLoadState`

---

## Batch 2 — Exception-swallow + commit hazard (5 sites)

### Category A — Log but continue (3 sites)

These sites keep their existing degraded behavior and only gain `frappe.log_error(frappe.get_traceback(), ...)` visibility.

#### 5. `ai/agent_integration.py:799` — knowledge context build

**Before:**

```python
        except Exception as e:
            frappe.log_error(
                f"Error building knowledge context: {str(e)}",
                "Knowledge Context Error"
            )
```

**After:**

```python
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Knowledge context build failed — agent run continuing without RAG context"
            )
```

**Behavior:** Agent still runs without RAG context; failure is now visible with a full traceback.

---

#### 6. `ai/agent_integration.py:944` — tool result JSON parse fallback

**Before:**

```python
                try:
                    tool_result = json.loads(raw.get("output")) if raw and raw.get("output") else None
                except Exception:
                    tool_result = raw.get("output")
```

**After:**

```python
                try:
                    tool_result = json.loads(raw.get("output")) if raw and raw.get("output") else None
                except (json.JSONDecodeError, TypeError):
                    frappe.log_error(
                        frappe.get_traceback(),
                        "Tool result JSON parse failed — using raw output"
                    )
                    tool_result = raw.get("output")
```

**Behavior:** Raw output is still used; failure is logged.

---

#### 7. `ai/flow_engine.py:916` — HTTP response JSON parse fallback

**Before:**

```python
            try:
                result_data = resp.json()
            except Exception:
                result_data = resp.text
```

**After:**

```python
            try:
                result_data = resp.json()
            except (json.JSONDecodeError, TypeError):
                frappe.log_error(
                    frappe.get_traceback(),
                    "HTTP response JSON parse failed — falling back to text"
                )
                result_data = resp.text
```

**Behavior:** Non-JSON responses still fall back to `resp.text`; failure is logged.

---

### Category B — Fail closed (2 sites)

These sites now abort the tool call instead of silently inserting a message at a potentially colliding `conversation_index`.

#### 8. `ai/sdk_tools.py:1555` — `handle_generate_image`

**Before:**

```python
            except Exception:
                conversation_index = 1
```

**After:**

```python
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Failed to compute conversation_index for {conversation_id}"
                )
                frappe.throw(
                    "Could not determine message order for this conversation. Please retry.",
                    title="Message Ordering Error"
                )
```

**Test:** `huf.ai.tests.test_p0_commit_hazards.TestP0CommitHazards.test_generate_image_fails_closed_when_index_query_raises`

---

#### 9. `ai/sdk_tools.py:2104` — `handle_generate_audio`

Same fail-closed pattern as site 8.

**Test:** `huf.ai.tests.test_p0_commit_hazards.TestP0CommitHazards.test_generate_audio_fails_closed_when_index_query_raises`

---

## Test execution

```bash
bench --site huf-new run-tests --app huf --module huf.ai.tests.test_p0_bare_except
bench --site huf-new run-tests --app huf --module huf.ai.tests.test_p0_commit_hazards
```

Both modules pass.

A full `bench --site huf-new run-tests --app huf` run is currently blocked by a pre-existing import failure in `huf/ai/knowledge/tests/test_chroma_backend.py`:

```
ModuleNotFoundError: No module named 'frappe.tests'; 'frappe' is not a package
```

This failure exists on the baseline `develop` branch and is unrelated to the P0 changes.

---

## Rollback

No schema or migration changes are involved. Rollback per batch is a plain `git revert <commit>` on the respective branch followed by redeploy.
