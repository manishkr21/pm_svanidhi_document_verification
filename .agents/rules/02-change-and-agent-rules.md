---
trigger: always_on
---

# Code Modification & AI Agent Rules

These rules define how changes must be made to the existing codebase.

## 1. Change Scope — CRITICAL

When asked to make a change:

* Change **only what is required** to complete the requested task.
* Do **not** modify unrelated code.
* Do **not** refactor unrelated code.
* Do **not** make additional "improvements" that were not requested.
* Do **not** change existing behaviour outside the requested functionality.
* Do **not** rename variables, functions, classes, files, or folders unless necessary.
* Do **not** reorganise project structure unless required.
* Do **not** reformat unrelated code.
* Do **not** reorder or clean unrelated imports.
* Do **not** remove existing functionality unless explicitly requested.
* Do **not** modify unrelated comments or documentation.
* Do **not** upgrade or replace dependencies unless required.
* Preserve backward compatibility wherever possible.

Always prefer the **smallest safe change** that solves the requested problem.

If a one-line change solves the problem safely, do not turn it into a large refactor.

## 2. Understand Before Editing

Before modifying code:

1. Read the relevant files.
2. Understand the current execution flow.
3. Identify the exact code responsible for the requested behaviour.
4. Search the codebase for similar functionality.
5. Check existing utilities, helpers, services, classes, constants, and schemas.
6. Identify callers and dependencies of the code being changed.
7. Consider how the change could affect existing functionality.
8. Determine the minimum set of files that must be modified.

Do not implement based purely on assumptions when the answer exists in the codebase.

## 3. Do Not Repeat Code

Follow DRY (Don't Repeat Yourself).

Before adding functionality:

* Search for an existing implementation.
* Reuse existing functions and utilities.
* Reuse existing constants and configuration.
* Reuse existing validation logic.
* Reuse existing schemas and models.
* Reuse existing services and abstractions.
* Extend existing functionality when appropriate instead of creating a parallel implementation.

Do **not**:

* Create duplicate functions.
* Duplicate business logic.
* Duplicate validation logic.
* Duplicate constants.
* Create multiple implementations of the same functionality.
* Copy-paste large blocks of existing code when they can be reused.

Do not introduce complicated abstractions merely to eliminate a few similar lines.

## 4. Preserve Existing Code

Treat existing working code as stable unless the requested task directly requires changing it.

Do not unnecessarily:

* Rewrite working functions.
* Change function signatures.
* Change class interfaces.
* Change API contracts.
* Change response structures.
* Change database schemas.
* Change configuration formats.
* Replace existing libraries.
* Rename identifiers.
* Move code between files.
* Delete existing functionality.

When existing code must be modified, make the minimum necessary modification.

## 5. No Unrequested Improvements

While working on a task, you may notice other problems.

Unless they directly prevent completion of the requested task:

* Do not fix them.
* Do not refactor them.
* Do not clean them up.
* Do not rename them.
* Do not optimise them.
* Do not change their formatting.

They may be mentioned separately if important, but must not be included in the implementation without approval.

## 6. No Unnecessary Code Generation

Do not create:

* Extra helper functions without need.
* Duplicate utility modules.
* Unnecessary wrapper classes.
* Unrequested configuration files.
* Unrequested documentation.
* Example files that were not requested.
* Backup copies of modified files.
* Alternative implementations.
* Dead or commented-out code.

Every new piece of code must have a clear purpose related to the requested task.

## 7. Refactoring

Refactoring should happen only when:

* Explicitly requested.
* Necessary to safely implement the requested functionality.
* Required to fix the demonstrated problem.

When refactoring:

* Preserve existing behaviour.
* Keep scope minimal.
* Do not combine unrelated refactoring with feature work.
* Avoid changing public interfaces.
* Ensure existing tests continue to pass.

Never use a small feature request as an excuse to rewrite unrelated code.

## 8. File Changes

Only create a new file when there is a clear reason.

Before creating a file, determine whether the functionality belongs in an existing file.

Do not:

* Create duplicate utility files.
* Create unnecessary helper modules.
* Move files unnecessarily.
* Delete files unless explicitly required.
* Modify unrelated files.

Follow the existing project structure.

Do not force a new architecture onto an established project.

## 9. When Requirements Are Unclear

Do not silently invent important requirements.

Ask for clarification if ambiguity could significantly affect:

* Architecture.
* Existing behaviour.
* API contracts.
* Database structure.
* Security.
* Data handling.
* Major implementation decisions.

For minor implementation details, choose the simplest solution consistent with the existing codebase.

## 10. Git Safety

Never automatically:

* Force push.
* Delete branches.
* Rewrite Git history.
* Perform destructive resets.
* Revert unrelated user changes.
* Commit secrets.
* Commit generated files unless expected by the project.

Do not undo changes that existed before the current task.

## 11. Required Agent Workflow

For every coding task:

1. Understand the request.
2. Inspect relevant code.
3. Understand the existing implementation.
4. Search for reusable functionality.
5. Identify the minimum necessary changes.
6. Implement only those changes.
7. Handle relevant edge cases.
8. Validate the implementation.
9. Run relevant tests/checks where possible.
10. Verify unrelated functionality remains unchanged.
11. Review the diff for accidental changes.
12. Summarise exactly what changed.

Do not make speculative changes for requirements that were not requested.

## 12. Final Verification

Before declaring the task complete, verify:

* The requested functionality is implemented.
* Only necessary files were changed.
* No unrelated code was modified.
* Existing functionality remains intact.
* No duplicate implementation was introduced.
* Existing utilities were reused where appropriate.
* No unnecessary abstraction was introduced.
* No unnecessary files were created.
* No unnecessary dependencies were added.
* No unrelated dependencies were changed.
* No secrets or sensitive data were introduced.
* Imports are valid.
* Syntax is valid.
* Error handling is appropriate.
* Relevant tests/checks pass.
* Public interfaces remain compatible unless intentionally changed.
* The final diff contains only changes related to the request.

## Most Important Rule

> **Make the smallest correct change required to fulfil the request. Do not modify, refactor, rename, remove, reformat, optimise, or "improve" anything unrelated to the requested task. Do not duplicate existing functionality. Always inspect and reuse the existing implementation before adding new code.**
