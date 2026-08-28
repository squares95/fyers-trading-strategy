from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

import Actions as Main

from .backfill import fetch_history_between
from .csv_store import CandleCsvStore


@dataclass(frozen=True)
class CandleValidationReport:
    compared_rows: int
    missing_local_rows: int
    missing_history_rows: int
    mismatch_rows: int
    max_abs_price_diff: float
    max_abs_volume_diff: int

    @property
    def passed(self) -> bool:
        return (
            self.missing_local_rows == 0
            and self.missing_history_rows == 0
            and self.mismatch_rows == 0
        )


def validate_local_1min_against_history(
    fyers,
    symbol: str,
    start_dt: datetime,
    end_dt: datetime,
    *,
    output_folder: str | Path = "./Data",
    price_tolerance: float = 0.05,
    volume_tolerance: int = 0,
) -> CandleValidationReport:
    store = CandleCsvStore(symbol, output_folder)
    local = _load_local_between(store.path(Main.TIMEFRAME_1MIN), start_dt, end_dt)
    reference = fetch_history_between(fyers, symbol, start_dt, end_dt)
    return compare_candle_frames(
        local,
        reference,
        price_tolerance=price_tolerance,
        volume_tolerance=volume_tolerance,
    )


def compare_candle_frames(
    local: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    price_tolerance: float = 0.05,
    volume_tolerance: int = 0,
) -> CandleValidationReport:
    local = Main.normalize_candles(local)
    reference = Main.normalize_candles(reference)
    merged = reference.merge(
        local, on="Datetime", how="outer", suffixes=("_history", "_local"), indicator=True
    )

    missing_local = int((merged["_merge"] == "left_only").sum())
    missing_history = int((merged["_merge"] == "right_only").sum())
    both = merged[merged["_merge"] == "both"].copy()
    if both.empty:
        return CandleValidationReport(0, missing_local, missing_history, 0, 0.0, 0)

    price_columns = ["Open", "High", "Low", "Close"]
    price_diffs = []
    for column in price_columns:
        diff = (both[f"{column}_history"] - both[f"{column}_local"]).abs()
        price_diffs.append(diff)
    max_price_diff = max(float(diff.max()) for diff in price_diffs)

    volume_diff = (both["Volume_history"] - both["Volume_local"]).abs()
    max_volume_diff = int(volume_diff.max())
    mismatch_mask = volume_diff > volume_tolerance
    for diff in price_diffs:
        mismatch_mask = mismatch_mask | (diff > price_tolerance)

    return CandleValidationReport(
        compared_rows=len(both),
        missing_local_rows=missing_local,
        missing_history_rows=missing_history,
        mismatch_rows=int(mismatch_mask.sum()),
        max_abs_price_diff=round(max_price_diff, 4),
        max_abs_volume_diff=max_volume_diff,
    )


def _load_local_between(path: str | Path, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)

    parts: list[pd.DataFrame] = []
    for chunk in pd.read_csv(file_path, parse_dates=["Datetime"], chunksize=100_000):
        rows = chunk[(chunk["Datetime"] >= start_dt) & (chunk["Datetime"] <= end_dt)]
        if not rows.empty:
            parts.append(rows[Main.RAW_COLUMNS])
    if not parts:
        return pd.DataFrame(columns=Main.RAW_COLUMNS)
    return Main.normalize_candles(pd.concat(parts, ignore_index=True))
