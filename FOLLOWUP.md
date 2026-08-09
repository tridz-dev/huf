# Follow-up: user status tri-state (Active / Invited / Suspended)

| Field | Value |
|---|---|
| Branch | `follow-up-user-status-tristate` |
| Branched from | `design-v3` @ `8f7fdcff` |
| Origin | [tridz-dev/huf#589](https://github.com/tridz-dev/huf/pull/589) (draft) — AppleQuietDesignSystem wave 8 |
| Track | `Tracks/AppleQuietDesignSystem` (this is a scoped-out follow-up of that track, not a separate track of its own) |
| Status | **Not started.** Branch exists with this doc and a `TODO` marker in the code; no implementation yet. |
| Merge target | `develop`, but only makes sense **after `design-v3`/PR #589 merges** — this branch's frontend diff is `design-v3`'s UsersPage.tsx plus a new backend field, so rebase onto `develop` once #589 lands rather than merging independently first. If #589 stalls, this can still be developed here and rebased later; just don't merge to `develop` ahead of it. |

## Why this exists

Wave 8 of the design-system track rebuilt `UsersPage.tsx`'s status column as a dot + label (spec: green=Active, amber=Invited, light-grey dot + dimmed row=Suspended). The **visual** pattern is built and shipped in PR #589. But the backend (`Huf User Role` doctype, via `huf/ai/permissions_api.py`) only exposes a boolean `enabled` field — so today the UI can only ever show **Active / Disabled**, a false two-state simplification of the spec's three states.

The gap is marked in code at [`frontend/src/pages/UsersPage.tsx:93`](frontend/src/pages/UsersPage.tsx#L93):
```ts
// TODO(user-status-tristate): the design spec's status dot vocabulary distinguishes
// Active / Invited / Suspended, but the backend only exposes a boolean `enabled` field
// today, so this only ever renders Active/Disabled. See branch follow-up-user-status-tristate.
```

## What already exists (don't rebuild)

- `huf/ai/permissions_api.py::get_users()` already returns `invited_by` and `invited_on` fields on `Huf User Role` (lines ~42-58) — these are already being tracked, just not surfaced as a status.
- `huf/ai/permissions_api.py::set_user_enabled(user, enabled)` (~line 142) is the existing toggle, now called from a confirm-dialog + row-menu in `UsersPage.tsx` (not a bare switch, per wave 8) — this flow doesn't need to change, it just needs a third state layered on top.
- Frontend dot-vocabulary rendering already exists at `UsersPage.tsx` (~lines 420-440) — `bg-good`/`bg-steel-soft` dot classes, `text-ink`/`text-steel` labels. Adding a third `Invited` visual state is a small addition to this same block, not new plumbing.
- The Roles & access capability matrix (`RolesPage.tsx`) is unrelated and doesn't need touching.

## What "Invited" vs "Suspended" actually mean (product definition to confirm, then implement)

The natural distinction, given what the backend already tracks:
- **Invited**: `enabled = 1`, `invited_on` is set, and the user has never actually logged in (no successful Frappe session yet for that user).
- **Active**: `enabled = 1` and the user has logged in at least once.
- **Suspended**: `enabled = 0` (i.e. today's "Disabled", renamed/re-themed to match the spec's word and the dimmed-row treatment).

This requires a "has this user ever logged in" signal Frappe already tracks natively (check `User.last_login`, or `Activity Log` for a first successful login event) — verify which is more reliable/available before building on it, rather than inventing a new field for something Frappe may already record.

## Implementation checklist (not yet started)

- [ ] Confirm the Invited/Active/Suspended definition above with the user (or re-derive it — this doc's version is a reasonable default, not a signed-off spec) before writing code.
- [ ] Backend: extend `get_users()` in `huf/ai/permissions_api.py` to compute and return a `status: "active" | "invited" | "suspended"` field per row, derived from `enabled` + `invited_on` + a real "ever logged in" signal (see above) — do NOT add a redundant status field to the doctype if it can be derived; only add a stored field if computing it live is expensive or the "ever logged in" signal turns out to be unreliable.
- [ ] Frontend: `UsersPage.tsx` — extend the status dot block to a 3-way switch (green/amber/light-grey per the spec, already documented in `Tracks/AppleQuietDesignSystem/DesignSystem/huf-design/project/HUF UI System.dc.html` section 30 "People & roles"), and dim the whole row (`opacity: .6` per spec) for Suspended.
- [ ] Frontend: `UserStatusFilter` type (`UsersPage.tsx:93`, right where the TODO lives) — extend `'all' | 'active' | 'disabled'` to include `'invited'`/`'suspended'` and wire the filter dropdown + `matchesStatus` predicate (~line 295) accordingly.
- [ ] Remove the `TODO(user-status-tristate)` comment once done.
- [ ] `tsc --noEmit` + `npm run build` clean, verified live against a bench (this follow-up should actually do the live-bench verification that wave 8 skipped — see `Tracks/AppleQuietDesignSystem/CONTEXT.md` infra notes for the bench sync flow).

## Context you'll need

- Design spec section 30 "People & roles": `Tracks/AppleQuietDesignSystem/DesignSystem/huf-design/project/HUF UI System.dc.html` (search for `id="members"`).
- Full wave 8 writeup, including this gap and why it was scoped out: `Tracks/AppleQuietDesignSystem/CONTEXT.md`, wave 8 entry.
- PR #589 diff for the full status-dot/row-menu UI this builds on top of.
