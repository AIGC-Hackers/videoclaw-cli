"""Tests for videoclaw.utils.retry.async_retry."""

import pytest

from videoclaw.utils.retry import async_retry


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """Should return immediately when fn succeeds on the first try."""
        calls = []

        async def fn():
            calls.append(1)
            return "ok"

        result = await async_retry(fn, max_attempts=3)
        assert result == "ok"
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_retries_and_succeeds(self):
        """Should succeed after initial failures within max_attempts."""
        calls = []

        async def fn():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("not yet")
            return "done"

        result = await async_retry(fn, max_attempts=5, catch=RuntimeError)
        assert result == "done"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        """Should re-raise the last exception when all attempts fail."""
        async def fn():
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            await async_retry(fn, max_attempts=3, catch=ValueError)

    @pytest.mark.asyncio
    async def test_propagates_uncaught_exception_immediately(self):
        """Exceptions not listed in 'catch' must propagate on first occurrence."""
        calls = []

        async def fn():
            calls.append(1)
            raise KeyError("unexpected")

        # catch=RuntimeError but fn raises KeyError — should not retry
        with pytest.raises(KeyError):
            await async_retry(fn, max_attempts=5, catch=RuntimeError)

        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_custom_backoff_fn(self):
        """backoff_fn controls sleep duration (we verify it's called correctly)."""
        backoff_calls: list[int] = []

        async def fn():
            raise RuntimeError("fail")

        def _backoff(attempt: int) -> float:
            backoff_calls.append(attempt)
            return 0.0  # zero sleep so test is fast

        with pytest.raises(RuntimeError):
            await async_retry(
                fn, max_attempts=3, catch=RuntimeError, backoff_fn=_backoff
            )

        # backoff called for attempts 1 and 2 (not after the final attempt)
        assert backoff_calls == [1, 2]

    @pytest.mark.asyncio
    async def test_tuple_catch(self):
        """catch= can be a tuple of exception types."""
        calls = []

        async def fn():
            calls.append(len(calls))
            if len(calls) == 1:
                raise ValueError("v")
            if len(calls) == 2:
                raise RuntimeError("r")
            return "good"

        result = await async_retry(
            fn, max_attempts=5, catch=(ValueError, RuntimeError), backoff_fn=lambda n: 0.0
        )
        assert result == "good"
        assert len(calls) == 3
