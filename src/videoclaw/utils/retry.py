"""Async retry utility — reusable exponential back-off helper.

Avoids copy-pasting the try/except/sleep pattern across adapters and
infrastructure components.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def async_retry(
    fn: Callable[[], Awaitable[T]],
    max_attempts: int,
    *,
    backoff_fn: Callable[[int], float] = lambda attempt: 1.0 * attempt,
    catch: type[Exception] | tuple[type[Exception], ...] = Exception,
    label: str = "",
) -> T:
    """Call *fn* up to *max_attempts* times, sleeping between failures.

    Parameters
    ----------
    fn:
        Zero-argument async callable to retry.
    max_attempts:
        Total number of attempts (including the first).
    backoff_fn:
        Maps ``attempt`` (1-indexed) to sleep duration in seconds.
        Defaults to ``attempt * 1.0`` (1s, 2s, 3s, …).
    catch:
        Exception type(s) that trigger a retry.  Other exceptions propagate
        immediately.
    label:
        Short description used in warning messages (e.g. ``"ffmpeg"``,
        ``"seedance create"``) for easier log scanning.

    Returns
    -------
    T
        The return value of *fn* on the first successful call.

    Raises
    ------
    Exception
        The last caught exception when all attempts are exhausted.
    """
    last_exc: Exception | None = None
    prefix = f"[{label}] " if label else ""

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except catch as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = backoff_fn(attempt)
                logger.warning(
                    "%sAttempt %d/%d failed: %s — retrying in %.1fs",
                    prefix, attempt, max_attempts, exc, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.warning(
                    "%sAttempt %d/%d failed: %s — giving up",
                    prefix, attempt, max_attempts, exc,
                )

    raise last_exc  # type: ignore[misc]
