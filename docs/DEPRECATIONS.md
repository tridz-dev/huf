# Deprecations

This document tracks deprecated features and their planned removal dates.

## run_scheduled_agents

**Module:** `huf.ai.agent_scheduler.run_scheduled_agents`

**Deprecated:** 2026-09-04

**Status:** Deprecated in favor of `huf.ai.automation_scheduler.run_automation_triggers` (the new automation runtime)

**Removal timeline:** One month after Remediation WP-08 ships and `automation_runtime_is_new()` is the default mode on all internal benches.

**Details:** The legacy scheduler path in `run_scheduled_agents()` is the pre-Remediation WP-08 implementation of scheduled agent execution. Once the new automation runtime (controlled by `automation_runtime_is_new()`) becomes mandatory, this function will be removed entirely. This function includes an idempotency guard for Batch Job submissions (ST-R4.5) as a bridge until the refactor completes.

**Action required:** After removal date, all callers should use `huf.ai.automation_scheduler.run_automation_triggers()` instead. The new path uses a queue-first architecture and is production-ready once WP-08 / ST-08.6 is verified on internal benches.

**Related:** Remediation WP-08 / ST-08.6, Residual WP-R4 / ST-R4.5 and ST-R4.6
