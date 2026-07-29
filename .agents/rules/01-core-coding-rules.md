---
trigger: always_on
---

# Core Python Development Rules

These rules apply to all Python code written, modified, reviewed, debugged, or refactored in this project.

## 1. Core Principles

* Write clean, readable, maintainable, production-quality Python.
* Follow PEP 8 and the existing coding style.
* Prefer simple and explicit solutions over clever or unnecessarily complex ones.
* Follow the existing project architecture and conventions.
* Understand the existing implementation before making changes.
* Reuse existing code wherever possible.
* Avoid unnecessary abstractions and over-engineering.
* Preserve existing behaviour unless explicitly asked to change it.

## 2. Python Standards

* Use the Python version defined by the project.
* Use meaningful variable, function, and class names.
* Prefer `pathlib.Path` for filesystem paths where practical.
* Use context managers for files and managed resources.
* Avoid unnecessary global state.
* Avoid mutable default arguments.
* Avoid wildcard imports.
* Remove unused imports introduced by your changes.
* Use constants instead of unexplained magic values where appropriate.

## 3. Functions

Functions should:

* Have one clear responsibility.
* Have descriptive names.
* Remain reasonably small.
* Prefer early returns over deeply nested conditions.
* Avoid unnecessary parameters.
* Use type hints where practical.
* Return predictable types.
* Handle relevant edge cases.

Do not create a new function if an existing function already performs the required operation.

## 4. Type Hints

Use type hints for:

* Function parameters.
* Return values.
* Important data structures.
* Public interfaces.

Example:

```python
def calculate_score(values: list[float]) -> float:
    ...
```

Avoid `Any` when a meaningful type can reasonably be specified.

Follow the existing project's typing conventions.

## 5. Classes

Use classes only when they represent meaningful state or behaviour.

* Keep classes focused.
* Prefer composition over unnecessary inheritance.
* Follow existing dependency-injection patterns.
* Avoid tightly coupling components.
* Do not introduce new base classes or interfaces without a clear need.

Do not create classes merely to group unrelated functions.

## 6. Error Handling

Never silently swallow errors.

Avoid:

```python
try:
    process()
except Exception:
    pass
```

Instead:

* Catch specific exceptions whenever possible.
* Provide useful error messages.
* Preserve useful debugging context.
* Follow existing project error-handling patterns.
* Handle expected failures explicitly.

Distinguish between:

* Validation errors.
* Business logic errors.
* External service errors.
* Database errors.
* Unexpected internal errors.

Broad `except Exception` blocks should only be used at justified application boundaries.

Never expose sensitive stack traces or internal details to API consumers.

## 7. Logging

Use the project's existing logging system.

If none exists, prefer Python's `logging` module over `print()`.

Do not add excessive logging.

Never log:

* Passwords.
* API keys.
* Authentication tokens.
* Credentials.
* Sensitive personal information.
* Sensitive document contents.

## 8. Configuration

Do not hardcode environment-specific configuration throughout the application.

Use the project's existing configuration mechanism for:

* API URLs.
* Credentials.
* Database connections.
* Model paths.
* Model names.
* Feature flags.
* Timeouts.
* Environment-specific settings.

Never commit secrets.

Use environment variables where appropriate.

## 9. Data Validation

Treat external data as untrusted.

Validate relevant:

* Required fields.
* Data types.
* Formats.
* Ranges.
* Enum values.
* File types.
* File sizes.
* Identifiers.

Use the project's existing validation framework when available.

Do not duplicate validation already performed reliably elsewhere.

## 10. File Handling

When handling files:

* Validate file types where necessary.
* Validate file sizes where necessary.
* Do not trust file extensions alone for security-sensitive validation.
* Use safe temporary locations.
* Clean temporary resources.
* Prevent path traversal.
* Avoid unexpected overwrites.
* Use context managers.
* Prefer `pathlib.Path` where practical.

Do not load extremely large files completely into memory unless necessary.

## 11. Security

Never:

* Hardcode credentials.
* Commit secrets.
* Expose authentication tokens.
* Expose internal stack traces through APIs.
* Execute untrusted input.
* Construct SQL using unsafe string concatenation.
* Disable security checks merely to make functionality work.
* Log sensitive information.

Use parameterised database queries.

Validate external input appropriately.

Follow existing authentication and authorisation mechanisms.

## 12. Async Code

Use asynchronous code only when appropriate.

Suitable cases include:

* Network requests.
* Database operations.
* External APIs.
* Other I/O-bound operations.

Do not:

* Convert code to async unnecessarily.
* Use async merely because the framework supports it.
* Perform significant blocking operations inside async handlers.

## 13. Dependencies

Before adding a dependency:

1. Check whether the project already has a suitable dependency.
2. Check whether the Python standard library can reasonably handle the task.
3. Add a new dependency only when justified.

Do not:

* Add packages for trivial functionality.
* Upgrade unrelated dependencies.
* Change dependency versions without reason.
* Replace existing libraries unnecessarily.

If a dependency is added or removed, update the appropriate dependency file.

## 14. Performance

Do not optimise prematurely.

Avoid obvious problems such as:

* Repeating expensive computations.
* Repeated database queries inside loops.
* Repeated external API calls for the same data.
* Loading large files unnecessarily.
* Repeatedly loading ML models.
* Processing data multiple times without need.

Cache expensive reusable resources only when appropriate.

Performance optimisation must not make the implementation unnecessarily complex.
