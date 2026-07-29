---
trigger: always_on
---

# API, Testing & Project Rules

## 1. API Development

When working with Python APIs:

* Validate all external input.
* Use explicit request and response schemas.
* Return appropriate HTTP status codes.
* Keep route/controller logic minimal.
* Keep business logic in the appropriate service layer when the architecture supports it.
* Maintain consistent response formats.
* Preserve existing API contracts unless explicitly asked to change them.
* Handle malformed requests gracefully.
* Handle external service failures.
* Set appropriate timeouts for external calls.

Prefer an architecture similar to:

```text
Route → Validation → Service → Repository / External Service
```

when consistent with the existing project.

Do not force this architecture onto a project following another reasonable pattern.

## 2. External APIs

External integrations must account for:

* Timeouts.
* Connection failures.
* Authentication failures.
* Invalid responses.
* Missing fields.
* Rate limits.
* Service outages.

Always set reasonable timeouts.

Do not assume external API responses always have the expected structure.

Only implement automatic retries when the operation is safe to retry.

## 3. Testing

Important functionality should be testable.

Tests should cover relevant:

* Normal behaviour.
* Invalid input.
* Boundary conditions.
* Failure scenarios.
* Edge cases.
* Regression cases.

When fixing a bug, add a regression test when practical.

Avoid tests that unnecessarily depend on:

* Real external APIs.
* Production databases.
* Network availability.
* Real credentials.

Mock external dependencies where appropriate.

Do not rewrite or modify unrelated tests.

## 4. Testing Existing Functionality

After making a change:

1. Test the requested functionality.
2. Run relevant existing tests.
3. Check affected integration points.
4. Verify existing behaviour remains unchanged.
5. Check important edge cases.
6. Check imports and syntax.
7. Check for unintended side effects.

Do not consider a task complete solely because the changed function runs successfully.

## 5. Comments and Documentation

Comments should explain **why**, not merely restate the code.

Use comments for:

* Non-obvious business rules.
* Workarounds.
* Complex algorithms.
* Important constraints.
* Decisions that might otherwise appear incorrect.

Use docstrings for public or complex functions/classes where useful.

Do not:

* Add excessive comments to self-explanatory code.
* Modify unrelated documentation.
* Generate large documentation files unless requested.

## 6. Project Structure

Always follow the existing project structure first.

For a new Python project, a structure such as this may be used:

```text
project/
├── src/
│   ├── api/
│   ├── services/
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   ├── utils/
│   └── config/
├── tests/
├── scripts/
├── requirements.txt
├── .env.example
└── README.md
```

Do not restructure an existing project merely to match this example.

## 7. Maintain Separation of Concerns

Where consistent with the existing architecture:

* Routes should handle HTTP concerns.
* Schemas should handle data structure and validation.
* Services should contain business logic.
* Repositories should handle persistence.
* Utilities should contain genuinely reusable helpers.
* Configuration should remain centralised.

Do not place unrelated responsibilities into the same function or class.

At the same time, do not introduce additional layers when the project does not need them.

## 8. Database Changes

When working with databases:

* Use parameterised queries.
* Follow existing ORM/database patterns.
* Avoid unnecessary queries.
* Avoid queries inside loops when they can be batched.
* Handle missing records appropriately.
* Preserve existing schemas unless modification is required.

Do not:

* Change tables or schemas unnecessarily.
* Delete data automatically.
* Run destructive migrations without explicit approval.
* Modify production data as part of ordinary code changes.

## 9. ML / AI Code

When working with ML models:

* Do not repeatedly load the same model for every request unless required.
* Reuse/cache model instances appropriately.
* Keep preprocessing consistent with model requirements.
* Validate input before inference.
* Handle model loading failures.
* Avoid unnecessary GPU/CPU transfers.
* Use inference mode where appropriate.
* Do not change model architecture, weights, thresholds, or preprocessing without a clear requirement.

Do not silently change confidence thresholds or decision logic.

## 10. Document Processing

For document-processing pipelines:

* Keep extraction, validation, matching, and response generation logically separated.
* Do not hardcode document-specific logic into generic pipeline code unless required.
* Prefer configurable schemas/rules for document-specific behaviour.
* Support multilingual input without assuming English-only text.
* Preserve original extracted values when transformations are performed.
* Track confidence scores where available.
* Handle missing and partially extracted fields gracefully.
* Do not assume every document contains every field.

Where appropriate, processing should conceptually follow:

```text
Input
  ↓
File Validation
  ↓
Document / Language Detection
  ↓
Text / Data Extraction
  ↓
Normalisation
  ↓
Field Mapping
  ↓
Validation / Matching
  ↓
Confidence Scoring
  ↓
Structured Response
```

The actual implementation should still follow the existing project's architecture.

## 11. Structured Responses

For APIs returning JSON:

* Keep response structures predictable.
* Use consistent field naming.
* Use appropriate data types.
* Avoid returning internal objects directly.
* Represent missing values consistently.
* Include error details in a structured format.
* Preserve backward compatibility where possible.

Do not add response fields merely because they may be useful in the future.

## 12. Final Quality Check

Before completion:

* Verify requested behaviour.
* Run relevant tests.
* Check edge cases.
* Check error handling.
* Check API compatibility.
* Check for unnecessary database/API calls.
* Check that no sensitive data is exposed.
* Check that no unrelated behaviour changed.
* Check that implementation follows existing project conventions.

A task is complete when the requested behaviour works correctly **without introducing unnecessary changes elsewhere**.
