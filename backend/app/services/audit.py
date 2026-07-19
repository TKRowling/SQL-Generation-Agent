from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class AuditService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def record(self, event: dict[str, Any]) -> None:
        path = Path(get_settings().audit_log_path)
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
        async with self._lock:
            await asyncio.to_thread(self._append, path, payload)

    @staticmethod
    def _append(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


audit_service = AuditService()
