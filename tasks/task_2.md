# Task 2: Simplify book-discovery walk in scan.py

## Problem
`scripts/scan.py` lines 168–214 — `walk_for_books()` is 47 lines with up to
5 levels of nesting. The decision tree for "is this a leaf? a disc pattern? a
mixed folder?" is hard to follow at a glance, and there are no comments
explaining the intent of each branch.

## Goal
Restructure `walk_for_books` using early-returns and optional helper predicates
to flatten the nesting to at most 3 levels.

## Acceptance criteria
1. `walk_for_books` body is ≤ 35 lines.
2. Nesting depth is ≤ 3 (measure by indentation).
3. Each branch has a one-line comment stating what case it handles.
4. Optionally extract `_has_disc_subdirs(path)` / `_collect_audio(path)` if
   they reduce repetition — but only if they're used in more than one place.
5. All existing tests pass unchanged.
6. Behaviour is identical to the original (same books discovered for the same
   directory trees).

## How to test
```bash
.venv/bin/pytest tests/ -q
```
The existing scan tests in `tests/test_scan.py` (or equivalent) must continue
to pass. If none exist, add at least one parametrized test covering:
- flat leaf folder
- disc-pattern folder (Disc 1 / Disc 2 subdirs)
- mixed folder (audio + subdirs, no disc pattern)
