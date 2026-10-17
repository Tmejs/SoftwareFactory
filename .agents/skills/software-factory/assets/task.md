# Task: <job-id>

## Objective
<Observable requested outcome>

## Scope
<Files or behavior in scope, and explicit boundaries>

## Context
<Relevant constraints and references needed by a fresh agent>

## Target repository
https://github.com/Tmejs/SoftwareFactory

## Baseline commit
<Full 40-character SHA from synchronized main>

## Acceptance criteria
- <Observable criterion>

## Checks
- unit: python3 -m unittest discover -s tests -v
- git-diff-check: git diff --check
