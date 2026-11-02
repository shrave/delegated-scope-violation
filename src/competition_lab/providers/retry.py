from __future__ import annotations

import time
from collections.abc import Callable


def bounded_retry[T](
    operation: Callable[[], T],
    *,
    retries: int,
    retryable: Callable[[Exception], bool],
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    for attempt in range(retries + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt == retries or not retryable(exc):
                raise
            sleep(min(2**attempt, 8))
    raise AssertionError("unreachable")
