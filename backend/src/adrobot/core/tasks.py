"""Helpers for running critical work to completion despite caller cancellation."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# Strong references prevent shielded tasks from being garbage-collected mid-flight.
_running_tasks: set[asyncio.Task[Any]] = set()


def _on_task_done(task: asyncio.Task[Any]) -> None:
    _running_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()  # Always retrieve so asyncio never warns "exception never retrieved".
    if exc is not None:
        logger.warning(
            "Shielded task %s ended with %s: %s", task.get_name(), type(exc).__name__, exc
        )


async def run_shielded[T](coro: Coroutine[Any, Any, T], *, name: str) -> T:
    """Run ``coro`` in its own task so a cancelled caller cannot interrupt it midway.

    If the caller is cancelled, ``CancelledError`` is raised in the caller only; the inner task
    keeps running to completion (its own failures are logged by the done-callback).
    """
    task = asyncio.create_task(coro, name=name)
    _running_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return await asyncio.shield(task)
