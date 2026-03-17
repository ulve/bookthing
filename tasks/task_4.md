# Task 4: Extract magic constants in app.js

## Problem
`static/app.js` scatters inline string and numeric literals throughout the file:

- Completion threshold `99` (and variants `>= 99`, `< 99`, `> 0`) appears 5+
  times with no named constant explaining the intent.
- Status strings `"listening"`, `"unlistened"`, `"completed"` are repeated in
  `renderLibrary`, `refreshLibraryView`, clear-filters logic, and elsewhere.
- Sort key strings `"newest"`, `"oldest"`, `"series"`, `"author"`, `"title"`
  are repeated wherever sort controls are read or written.

## Goal
Define named constants near the top of `app.js` and replace all inline
occurrences.

## Acceptance criteria
1. Near the top of `app.js` (before any function definitions), add:
   ```js
   const COMPLETED_PCT = 99;

   const STATUS = {
     LISTENING:   "listening",
     UNLISTENED:  "unlistened",
     COMPLETED:   "completed",
   };

   const SORT = {
     NEWEST: "newest",
     OLDEST: "oldest",
     SERIES: "series",
     AUTHOR: "author",
     TITLE:  "title",
   };
   ```
2. Every inline occurrence of these literals is replaced with the constant.
3. No functional change — app behaviour is identical.
4. All existing JS-related tests (if any) pass.

## How to test
Manual: open the app, verify filtering/sorting/status badges work correctly.
Grep check:
```bash
grep -n '"listening"\|"unlistened"\|"completed"\|"newest"\|"oldest"\|"series"\|"author"\|"title"' static/app.js
```
Should return only the constant definitions themselves, not scattered usages.
