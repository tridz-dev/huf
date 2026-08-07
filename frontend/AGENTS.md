# frontend/AGENTS.md

Local rules for `frontend/` only — see the root [`../AGENTS.md`](../AGENTS.md) for repository-wide
instructions; don't repeat them here.

- Read [`../docs/architecture/frontend.md`](../docs/architecture/frontend.md) and
  [`../DESIGN.md`](../DESIGN.md) before changing shared UI patterns or components.
- Keep TypeScript strict. Unused variables, unresolved imports, and unused functions fail the
  build (`error TS6133`). After any refactor, proactively remove now-unused code rather than
  leaving it for the build to catch — and never weaken `tsconfig` or ESLint rules just to get a
  build to pass.
- Before considering frontend work done, run:
  ```bash
  npm run typecheck && npm run lint && npm run test
  ```
- User-facing text (labels, placeholders, empty states, errors) must read as plain product copy —
  never leak backend mechanics. Write "Search records..." not "Search API records...", "Filter..."
  not "Filter columns locally...". If unsure whether a string is user-facing, write it assuming
  the reader has never heard of Frappe, DocTypes, REST, or SSE.
- Preserve accessibility behavior (focus handling, ARIA attributes, keyboard nav) when changing
  shared UI primitives in `components/`.
- Package versions and dependency lists are not documented here — they drift immediately and
  `package.json` is always correct; check it directly instead of trusting prose about it.
