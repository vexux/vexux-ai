"""Generic workflow execution contracts."""

from __future__ import annotations


class WorkflowExecutionError(RuntimeError):
    """A workflow failure with explicit control-flow semantics."""

    def __init__(
        self,
        message: str,
        *,
        terminal: bool = False,
        retryable: bool = True,
        authoritative: bool = False,
        failure_category: str | None = None,
    ):
        super().__init__(message)
        self.terminal = terminal
        self.retryable = retryable
        self.authoritative = authoritative
        self.failure_category = failure_category
