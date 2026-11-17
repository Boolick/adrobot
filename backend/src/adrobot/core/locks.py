"""Process-local keyed asyncio locks used to serialize conflicting mutations.

These locks protect a single worker process only. Cross-process safety relies on the
database unique constraints and snapshot checks implemented in the services.
"""

import asyncio
from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass
class _Entry:
    lock: asyncio.Lock
    users: int = 0


class KeyedLockRegistry:
    """Hand out one `asyncio.Lock` per key and drop idle entries to avoid unbounded growth."""

    def __init__(self) -> None:
        self._entries: dict[Hashable, _Entry] = {}

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncGenerator[None]:
        """Hold the lock for ``key`` for the duration of the ``async with`` block."""
        entry = self._entries.get(key)
        if entry is None:
            entry = _Entry(lock=asyncio.Lock())
            self._entries[key] = entry
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if entry.users == 0:
                self._entries.pop(key, None)

    def __len__(self) -> int:
        return len(self._entries)


stream_locks = KeyedLockRegistry()
campaign_locks = KeyedLockRegistry()
campaign_name_locks = KeyedLockRegistry()
