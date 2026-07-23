"""Process boundary for parsing untrusted PDF content."""

import multiprocessing
import resource
from multiprocessing.connection import Connection
from typing import Literal

from app.modules.policy.models import ParsedDocument
from app.modules.policy.parsing import (
    PdfComplexityLimitExceededError,
    PdfPageLimitExceededError,
    PdfPasswordIncorrectError,
    PdfPasswordRequiredError,
    parse_document,
)

PDF_PARSE_TIMEOUT_SECONDS = 30
PDF_PARSE_CPU_LIMIT_SECONDS = 25
PDF_PARSE_MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024

type _ParseStatus = Literal[
    "ok",
    "password_required",
    "password_incorrect",
    "page_limit",
    "complexity_limit",
]


class PdfParserResourceLimitExceededError(PdfComplexityLimitExceededError):
    """The isolated parser exceeded its wall-time or process resource budget."""


def parse_document_isolated(
    pdf_bytes: bytes,
    password: str | None = None,
) -> ParsedDocument:
    """Parse a PDF in a killable process with CPU, memory, and wall-time limits."""

    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_parse_worker,
        args=(send, pdf_bytes, password),
        daemon=True,
    )
    process.start()
    send.close()

    try:
        if not receive.poll(PDF_PARSE_TIMEOUT_SECONDS):
            raise PdfParserResourceLimitExceededError
        try:
            status, result = receive.recv()
        except EOFError:
            raise PdfParserResourceLimitExceededError from None
    finally:
        receive.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)

    if status == "ok" and isinstance(result, ParsedDocument):
        return result
    if status == "password_required":
        raise PdfPasswordRequiredError
    if status == "password_incorrect":
        raise PdfPasswordIncorrectError
    if status == "page_limit":
        raise PdfPageLimitExceededError
    if status == "complexity_limit":
        raise PdfComplexityLimitExceededError
    raise PdfParserResourceLimitExceededError


def _parse_worker(
    connection: Connection,
    pdf_bytes: bytes,
    password: str | None,
) -> None:
    try:
        _apply_process_limits()
        try:
            result = parse_document(pdf_bytes, password=password)
        except PdfPasswordRequiredError:
            _send_result(connection, "password_required")
        except PdfPasswordIncorrectError:
            _send_result(connection, "password_incorrect")
        except PdfPageLimitExceededError:
            _send_result(connection, "page_limit")
        except PdfComplexityLimitExceededError:
            _send_result(connection, "complexity_limit")
        else:
            connection.send(("ok", result))
    finally:
        connection.close()


def _send_result(connection: Connection, status: _ParseStatus) -> None:
    connection.send((status, None))


def _apply_process_limits() -> None:
    _set_limit(resource.RLIMIT_CPU, PDF_PARSE_CPU_LIMIT_SECONDS)
    _set_limit(resource.RLIMIT_AS, PDF_PARSE_MEMORY_LIMIT_BYTES)


def _set_limit(resource_kind: int, limit: int) -> None:
    try:
        current_soft, current_hard = resource.getrlimit(resource_kind)
        hard_limit = limit if current_hard == resource.RLIM_INFINITY else min(limit, current_hard)
        soft_limit = min(limit, hard_limit)
        resource.setrlimit(resource_kind, (soft_limit, hard_limit))
    except (OSError, ValueError):
        # The parent wall-time and forced termination still bound platforms that
        # do not support one of these POSIX resource limits.
        return
