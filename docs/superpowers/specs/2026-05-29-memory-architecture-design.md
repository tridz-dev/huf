# Memory Architecture Design

**Date:** 2026-05-29
**Status:** Approved
**Outcome:** Phase plan and RFC updated. Phase 1 (PR #275) hardening next.

---

## Decisions made

### Backend coupling
Memory Record → Knowledge Source → Backend (loose). Memory tools never reference backend types. New backends (pg_vector, Qdrant) implemented as `KnowledgeBackend` subclasses. Zero memory layer changes needed.

### Memory Policy activation
Phase 2: Agent-linked policy + site-wide default. Resolver chain: Agent Policy → Site Default → built-in safe defaults. Enforcement of inject_mode and token_budget first.

### Learning model
Hybrid: tool-driven saves now (Phase 1), policy-triggered extraction in Phase 3. Granular triggers: End of Conversation, Every N Turns, Manual. Optional delegation to a Learning Agent (a regular HUF Agent with specialized prompt). Draft-first by default.

### Output
- Updated `docs/SCOPED_MEMORY_KNOWLEDGE_BRIDGE_RFC.md` — corrected, reflects live backends + phases
- New `docs/memory/zero-to-hero.md` — full intellectual context doc for new contributors
- New `docs/memory/phase-plan.md` — per-phase delivery plan with definition of done

---

## Documents produced

- [RFC](../../SCOPED_MEMORY_KNOWLEDGE_BRIDGE_RFC.md)
- [Zero to Hero](../../memory/zero-to-hero.md)
- [Phase Plan](../../memory/phase-plan.md)
