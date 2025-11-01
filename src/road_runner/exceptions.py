"""Custom exception hierarchy."""

from __future__ import annotations


class RoadRunnerError(Exception):
    """Base exception for the road_runner package."""


class ValidationError(RoadRunnerError):
    """Raised when configuration validation fails."""


class SafetyViolationError(ValidationError):
    """Raised when a safety policy is violated."""


class AdapterExecutionError(RoadRunnerError):
    """Raised when an adapter fails during execution."""
