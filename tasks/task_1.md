# Task 1: Extract listening-session algorithm from main.py

## Problem
`app/main.py` lines 424–471 contain a ~50-line algorithm embedded directly inside
the `get_listening_sessions` API endpoint. This makes the logic hard to test
in isolation and the function hard to read.

Specific issues:
- Two magic constants (`GAP = 300`, `HEARTBEAT_CREDIT = 5`) are defined inside
  the endpoint with only terse inline comments — the *why* is unclear.
- The session-flush logic is duplicated: lines 445–447 (gap branch) and
  lines 466–468 (final close) are identical `append` calls.

## Goal
Extract `aggregate_listening_sessions(rows)` as a standalone pure function
defined above the endpoint. The endpoint body becomes a thin DB fetch + call.

## Acceptance criteria
1. `aggregate_listening_sessions(rows)` exists as a module-level function in
   `app/main.py` (or a new `app/sessions.py` if preferred).
2. The function has a docstring explaining:
   - what `GAP` represents and why 300 s was chosen
   - what `HEARTBEAT_CREDIT` represents and why 5 s was chosen
   - the minimum-30-second threshold for emitting a session
3. The flush logic (append + reset) appears exactly once, called from both the
   gap branch and the end-of-loop close.
4. The endpoint `get_listening_sessions` delegates entirely to the new function.
5. Existing behaviour is unchanged (all current tests pass).

## How to test
```bash
.venv/bin/pytest tests/ -q
```
Optionally add a unit test `tests/test_sessions.py` that exercises
`aggregate_listening_sessions` directly with synthetic row dicts.
