# Task 6: Deduplicate test fixtures and add missing edge-case tests

## Problem
### Duplicated fixture logic
`tests/conftest.py` lines 86–141: `auth_client` and `admin_client` each repeat
the same pattern of inserting a user row, creating a session token, setting the
session cookie. The duplication means a schema change requires two edits.

### Missing sort tests
`tests/test_books.py` has no tests for the `sort` query parameter introduced
with the sort-controls feature (`newest`, `oldest`, `series`, `author`, `title`).

### Missing auth-boundary test
`tests/test_api.py` has no test asserting that a non-admin user receives 403
when hitting an admin-only endpoint (e.g. `POST /api/admin/scan`).

## Goal
Share fixture logic; add ~5 focused new tests.

## Acceptance criteria

### Fixtures
1. A private helper `_insert_user_session(client, db, email, is_admin)` (or
   equivalent) in `conftest.py` reduces duplication between `auth_client` and
   `admin_client`.
2. Both fixtures still work identically from the callers' perspective.

### Sort tests (tests/test_books.py or tests/test_api.py)
3. Test `sort=newest` returns books ordered by `added_at` descending.
4. Test `sort=oldest` returns books ordered by `added_at` ascending.
5. Test `sort=title` returns books ordered alphabetically by title.
6. Test `sort=author` returns books ordered by author name.
7. (Optional) Test `sort=series` returns books grouped by series.

### Auth boundary test
8. A non-admin authenticated user hitting `POST /api/admin/scan` receives
   HTTP 403.

## How to test
```bash
.venv/bin/pytest tests/ -q
```
All new and existing tests must pass.
