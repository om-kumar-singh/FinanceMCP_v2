"""
Lightweight in-memory conversation memory for /chat.

We keep it best-effort (no external storage) to avoid new infra.
Keyed by a client identifier (X-Session-Id header if present, else client IP).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class _Entry:
    updated_at: float
    data: Dict[str, Any] = field(default_factory=dict)


_STORE: dict[str, _Entry] = {}
_TTL_SECONDS = 20 * 60  # 20 minutes
_MAX_KEYS = 2000


def _prune(now: Optional[float] = None) -> None:
    t = now or time.time()
    expired = [k for k, v in _STORE.items() if (t - v.updated_at) > _TTL_SECONDS]
    for k in expired:
        _STORE.pop(k, None)

    # Size cap: remove oldest entries
    if len(_STORE) > _MAX_KEYS:
        oldest = sorted(_STORE.items(), key=lambda kv: kv[1].updated_at)[: max(1, len(_STORE) - _MAX_KEYS)]
        for k, _ in oldest:
            _STORE.pop(k, None)


def get_context(client_id: str | None) -> Dict[str, Any]:
    if not client_id:
        return {}
    _prune()
    entry = _STORE.get(client_id)
    if not entry:
        return {}
    return dict(entry.data)


def update_context(client_id: str | None, **updates: Any) -> Dict[str, Any]:
    if not client_id:
        return {}
    _prune()
    entry = _STORE.get(client_id)
    if not entry:
        entry = _Entry(updated_at=time.time(), data={})
        _STORE[client_id] = entry
    entry.updated_at = time.time()
    entry.data.update({k: v for k, v in updates.items() if v is not None})
    return dict(entry.data)

