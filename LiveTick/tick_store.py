from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from .candle_builder import TickRecord, normalize_expected_symbol


IST = ZoneInfo("Asia/Kolkata")


def safe_symbol_folder_name(symbol: str) -> str:
    normalized = normalize_expected_symbol(symbol)
    return normalized.split(":", 1)[-1].replace("-EQ", "").replace(":", "_").replace("/", "_")


class TickJsonlStore:
    def __init__(self, symbol: str, root: str | Path) -> None:
        self.symbol = normalize_expected_symbol(symbol)
        self.folder = Path(root) / safe_symbol_folder_name(symbol)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._file_date = None
        self._handle = None
        self.rows_written = 0

    def write(self, raw_message: Any, tick: TickRecord | None) -> None:
        now = datetime.now(IST).replace(tzinfo=None)
        tick_date = tick.timestamp.date() if tick is not None else now.date()
        record = {
            "stored_at": now.isoformat(sep=" "),
            "symbol": self.symbol,
            "tick": tick.to_jsonable() if tick is not None else None,
            "raw": raw_message,
        }
        line = json.dumps(record, default=str, separators=(",", ":"))
        with self._lock:
            self._rotate(tick_date)
            self._handle.write(line + "\n")
            self._handle.flush()
            self.rows_written += 1

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None
                self._file_date = None

    def _rotate(self, tick_date) -> None:
        if self._handle is not None and self._file_date == tick_date:
            return
        if self._handle is not None:
            self._handle.close()
        path = self.folder / f"{tick_date:%Y-%m-%d}_ticks.jsonl"
        self._handle = path.open("a", encoding="utf-8")
        self._file_date = tick_date
