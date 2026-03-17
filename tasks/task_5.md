# Task 5: Split renderAdmin() into named inner helpers

## Problem
`static/app.js` — `renderAdmin()` is ~968 lines (approximately lines 687–1655).
The three inner table-render functions (`renderAdminTable`, `renderEmailsTable`,
`renderUsersTable`) are already named, but two large blocks of event-wiring code
are anonymous inline blocks:

- Bulk-edit panel wiring (~lines 1100–1260): dozens of `addEventListener` calls
  for the bulk-edit sidebar, with no named boundary.
- Tag-tools wiring (~lines 1420–1530): event wiring for rename/remove/merge tag
  operations, similarly anonymous.

These anonymous blocks make it hard to navigate the function or find where a
specific event listener is attached.

## Goal
Extract the two anonymous wiring blocks into named inner functions, called once
at the bottom of `renderAdmin`. No state restructuring needed — they are pure
extractions.

## Acceptance criteria
1. `function wireBulkPanel() { ... }` exists as a named inner function inside
   `renderAdmin`, containing the bulk-edit event listeners.
2. `function wireTagTools() { ... }` exists as a named inner function inside
   `renderAdmin`, containing the tag rename/remove/merge listeners.
3. Both functions are called at the end of `renderAdmin` (or inline at the point
   where they previously appeared — either is fine as long as they're named).
4. No functional change — all admin UI interactions work identically.
5. Total line count of `renderAdmin` does not increase.

## How to test
Manual: open admin page, verify bulk-edit panel and tag tools (rename, remove)
still work correctly.
```bash
.venv/bin/pytest tests/ -q
```
