"""Service / domain layer.

Pure data functions extracted from route handlers so business logic is reusable
and unit-testable, and so heavy reads use batched queries instead of per-row
loops. Routes become thin controllers: parse request → call a service → shape
the response.
"""
