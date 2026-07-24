"""PII-safe metadata for developer-facing error diagnostics."""

from pathlib import Path
from traceback import extract_tb

_MAX_STACK_FRAMES = 12


def safe_exception_context(exc: BaseException) -> dict[str, object]:
    """Return useful failure context without exception text or local values."""

    frames = extract_tb(exc.__traceback__, limit=_MAX_STACK_FRAMES)
    safe_stack = tuple(
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames
    )
    return {
        "error_type": type(exc).__name__,
        "safe_stack": safe_stack,
    }
