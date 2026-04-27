"""Structlog-based tracing processor for OpenAI Agents SDK.

Converts SDK trace/span events into structlog entries, providing
a unified audit trail for agent execution.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import structlog

from agents.tracing import (
    TracingProcessor,
    Trace,
    Span,
)

logger = structlog.get_logger("lacquertutor.tracing")


class StructlogTracingProcessor(TracingProcessor):
    """Routes SDK tracing events to structlog.

    Each span (tool call, LLM call, handoff, guardrail) is logged
    with structured fields for downstream analysis.
    """

    def __init__(self) -> None:
        self._active_spans: dict[str, float] = {}  # span_id → start_time

    def on_trace_start(self, trace: Trace) -> None:
        logger.info(
            "trace_start",
            trace_id=trace.trace_id,
            name=trace.name,
        )

    def on_trace_end(self, trace: Trace) -> None:
        logger.info(
            "trace_end",
            trace_id=trace.trace_id,
            name=trace.name,
        )

    def on_span_start(self, span: Span[Any]) -> None:
        self._active_spans[span.span_id] = time.monotonic()
        logger.debug(
            "span_start",
            span_id=span.span_id,
            span_type=type(span).__name__,
        )

    def on_span_end(self, span: Span[Any]) -> None:
        start = self._active_spans.pop(span.span_id, None)
        duration_ms = (time.monotonic() - start) * 1000 if start else 0

        # Extract span-type-specific info
        span_data: dict[str, Any] = {
            "span_id": span.span_id,
            "span_type": type(span).__name__,
            "duration_ms": round(duration_ms, 1),
        }

        # Try to get span-specific attributes
        if hasattr(span, "span_data"):
            data = span.span_data
            if hasattr(data, "name"):
                span_data["name"] = data.name
            if hasattr(data, "input"):
                span_data["input_preview"] = str(data.input)[:100]
            if hasattr(data, "output"):
                span_data["output_preview"] = str(data.output)[:100]

        logger.info("span_end", **span_data)

    def shutdown(self) -> None:
        """Clean up resources."""
        self._active_spans.clear()

    def force_flush(self) -> None:
        """Force flush any pending spans."""
        pass


def setup_tracing(enabled: bool = True) -> None:
    """Configure SDK tracing with structlog processor.

    Args:
        enabled: If False, disables all tracing.
    """
    from agents.tracing import set_tracing_disabled, set_trace_processors

    if not enabled:
        set_tracing_disabled(True)
        return

    set_tracing_disabled(False)
    # Replace default processors (which try to send to OpenAI) with our structlog one
    set_trace_processors([StructlogTracingProcessor()])
    logger.info("Tracing enabled with StructlogTracingProcessor")
