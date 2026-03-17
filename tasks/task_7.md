# Task 7: Fix auth.py rate-limit memory leak

## Problem
`app/auth.py` line 15:
```python
_last_sent: dict[str, float] = {}
```
This dictionary is never pruned. Every distinct email address that requests a
magic link is stored forever. On a long-running server with many login attempts
(legitimate or otherwise), this accumulates without bound.

## Goal
Prune stale entries before each insert so the dict stays bounded.

## Acceptance criteria
1. Before inserting a new `_last_sent[email] = now` entry, remove all entries
   where `now - timestamp > _RATE_LIMIT_SECONDS`.
2. The prune is a single loop (or dict comprehension) — no external dependencies.
3. Rate-limiting behaviour is unchanged: an address that was sent a link within
   the last 600 s is still rejected.
4. All existing tests pass.

## Implementation hint
```python
# prune old entries
now = time.time()
_last_sent.update({k: v for k, v in _last_sent.items() if now - v <= _RATE_LIMIT_SECONDS})
# or equivalently:
for k in [k for k, v in _last_sent.items() if now - v > _RATE_LIMIT_SECONDS]:
    del _last_sent[k]
```
The prune should happen in `request_magic_link`, just before the rate-limit
check, so the check itself is unaffected.

## How to test
```bash
.venv/bin/pytest tests/ -q
```
Optionally add a unit test that:
1. Populates `_last_sent` with a stale entry (timestamp far in the past).
2. Calls `request_magic_link` for a new address.
3. Asserts the stale entry has been removed from `_last_sent`.
