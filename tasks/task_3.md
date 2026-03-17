# Task 3: Add CSS custom properties for repeated values

## Problem
`static/style.css` has several groups of magic literals repeated in many places:

### Accent-colour transparencies
`:root` already defines `--accent` but not transparency variants.
Raw `rgba(...)` calls for accent at ~3 different opacities appear in ~8 rules.

### Transition durations
Four distinct durations (0.1 s, 0.12 s, 0.15 s, 0.3 s) are hardcoded on
`transition:` lines throughout the file with no named variables.

### Breakpoints
Media queries use several similar breakpoints (560 px, 600 px, 680 px, 700 px)
without a consistent set of named values. (CSS custom properties cannot be used
inside `@media`, so this is a documentation/comment improvement only.)

## Goal
Zero visual changes. Only add variables and replace literals.

## Acceptance criteria
1. `:root` block gains:
   - `--accent-bg-strong` (opacity ~0.18 variant)
   - `--accent-bg-mid`    (opacity ~0.10 variant)
   - `--accent-bg-subtle` (opacity ~0.04 variant)
   - `--transition-fast`  (≈ 0.1 s)
   - `--transition-normal`(≈ 0.15 s)
   - `--transition-slow`  (≈ 0.3 s)
2. All `rgba(...)` accent-transparency literals are replaced with the new vars.
3. All `transition:` duration literals are replaced with the new vars.
4. Breakpoint values are left as-is in `@media` queries (CSS limitation) but a
   comment block near `:root` documents the canonical breakpoint values.
5. No change in rendered appearance — verify manually in browser.

## How to test
Visual check: open the app in a browser and confirm no styling regressions.
Automated: `grep -n 'rgba' static/style.css` should return only uses of the
new named variables (or zero raw rgba accent calls).
