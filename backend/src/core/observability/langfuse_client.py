"""
Langfuse observability client — singleton lifecycle, span helpers, trace context.

Uses langfuse 4.x API (no langfuse_context; uses client methods + OTel context).
"""
from __future__ import annotations

import contextvars
from typing import Any

from langfuse import Langfuse, observe as _observe, propagate_attributes

from ...core.config import get_settings
from ...utils.logger import logger

_client: Langfuse | None = None


def init_langfuse() -> Langfuse | None:
    """Initialise the Langfuse client from application settings.

    Safe to call multiple times — only the first call creates the client.
    """
    global _client
    settings = get_settings()
    if not settings.langfuse_enabled:
        logger.info("Langfuse disabled — no traces will be sent")
        return None
    if _client is not None:
        return _client
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning(
            "Langfuse enabled but credentials missing — tracing is a no-op"
        )
        return None
    _client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    logger.info("Langfuse client initialised  host=%s", settings.langfuse_host)
    return _client


def get_client() -> Langfuse | None:
    """Return the singleton client (may be None if disabled)."""
    return _client


def flush() -> None:
    """Flush any pending events. Call before process exit."""
    if _client is not None:
        try:
            _client.flush()
        except Exception:
            pass


def shutdown() -> None:
    """Flush + shutdown the client."""
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Trace-level attribute propagation
# ---------------------------------------------------------------------------

def trace_attributes(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, str] | None = None,
    tags: list[str] | None = None,
    trace_name: str | None = None,
):
    """Context manager that propagates attributes to all spans in the current trace.

    Usage::

        with trace_attributes(user_id="123", session_id="abc"):
            result = await chat_service.chat(...)
    """
    return propagate_attributes(
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
        tags=tags,
        trace_name=trace_name,
    )


# ---------------------------------------------------------------------------
# Current-span helpers
# ---------------------------------------------------------------------------

def get_current_trace_id() -> str | None:
    """Return the OTel trace id for the innermost active span, if any."""
    cl = _client
    if cl is None:
        return None
    try:
        return cl.get_current_trace_id()
    except Exception:
        return None


def update_current_span(
    *,
    name: str | None = None,
    input: Any = None,
    output: Any = None,
    metadata: Any = None,
    level: str | None = None,
    status_message: str | None = None,
) -> None:
    """Update the innermost active span."""
    cl = _client
    if cl is None:
        return
    try:
        cl.update_current_span(
            name=name,
            input=input,
            output=output,
            metadata=metadata,
            level=level,
            status_message=status_message,
        )
    except Exception:
        pass


def update_current_generation(
    *,
    name: str | None = None,
    input: Any = None,
    output: Any = None,
    metadata: Any = None,
    model: str | None = None,
    model_parameters: dict[str, Any] | None = None,
    usage_details: dict[str, int] | None = None,
    cost_details: dict[str, float] | None = None,
    level: str | None = None,
    status_message: str | None = None,
) -> None:
    """Update the innermost active *generation* span with LLM-specific fields."""
    cl = _client
    if cl is None:
        return
    try:
        cl.update_current_generation(
            name=name,
            input=input,
            output=output,
            metadata=metadata,
            model=model,
            model_parameters=model_parameters,
            usage_details=usage_details,
            cost_details=cost_details,
            level=level,
            status_message=status_message,
        )
    except Exception:
        pass


def score_current_trace(
    name: str,
    value: float,
    comment: str | None = None,
) -> None:
    """Attach a score (0-1) to the current trace for eval purposes."""
    cl = _client
    if cl is None:
        return
    try:
        cl.score_current_trace(name=name, value=value, comment=comment)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Re-export the upstream decorator so callers only import this module.
# ---------------------------------------------------------------------------

def observe(*args: Any, **kwargs: Any) -> Any:
    """Thin wrapper around ``langfuse.observe``.

    Usage::

        from .observability.langfuse_client import observe

        @observe()
        async def my_llm_call(messages):
            ...

        @observe(as_type="generation")
        async def my_llm_call(messages):
            ...
    """
    kwargs.setdefault("as_type", "generation")
    return _observe(*args, **kwargs)
