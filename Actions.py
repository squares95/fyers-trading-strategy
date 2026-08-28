from __future__ import annotations

from pathlib import Path

import Download as _Download
import MutualFunds as _MutualFunds
from Download import (
    MaterializeTimeframeFiles,
    WriteTimeframeFiles,
    base_1min_input_path,
    materialize_timeframe_files,
    read_existing_candles,
    resolve_fyers_symbol,
    ta,
    write_timeframe_files,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_FOLDER = str(ROOT / "Data")


def login():
    from Login import login as FyersLogin

    return FyersLogin()


def Login():
    return login()


def add_indicators(df, log_fn=None):
    original_ta = _Download.ta
    _Download.ta = ta
    try:
        return _Download.add_indicators(df, log_fn)
    finally:
        _Download.ta = original_ta


def AddIndicators(df, log_fn=None):
    return add_indicators(df, log_fn)


def download(
    symbols, output_folder=DEFAULT_DATA_FOLDER, chunk_days=100, total_days=365, downloadStats=False
):
    original_login = _Download.login
    original_ta = _Download.ta
    _Download.login = login
    _Download.ta = ta
    try:
        return _Download.download(symbols, output_folder, chunk_days, total_days, downloadStats)
    finally:
        _Download.login = original_login
        _Download.ta = original_ta


def Download(
    symbols, output_folder=DEFAULT_DATA_FOLDER, chunk_days=100, total_days=365, downloadStats=False
):
    return download(symbols, output_folder, chunk_days, total_days, downloadStats)


def DownloadMutualFund(
    fund_name: str = _MutualFunds.DEFAULT_FUND,
    *,
    output_folder=DEFAULT_DATA_FOLDER,
    timeout: int = 30,
    retries: int = 3,
):
    return _MutualFunds.DownloadMutualFund(
        fund_name,
        output_folder=output_folder,
        timeout=timeout,
        retries=retries,
    )


def write_timeframe_files(symbol, output_folder, df_1min, progress_callback=None, log_fn=None):
    original_ta = _Download.ta
    _Download.ta = ta
    try:
        return _Download.write_timeframe_files(
            symbol, output_folder, df_1min, progress_callback, log_fn
        )
    finally:
        _Download.ta = original_ta


def WriteTimeframeFiles(symbol, output_folder, df_1min, progress_callback=None, log_fn=None):
    return write_timeframe_files(symbol, output_folder, df_1min, progress_callback, log_fn)


def materialize_timeframe_files(symbol: str, output_folder=DEFAULT_DATA_FOLDER):
    input_path = base_1min_input_path(symbol, output_folder)
    df_1min = read_existing_candles(input_path)
    if df_1min.empty:
        raise FileNotFoundError(f"No existing 1-minute data found for {symbol} at {input_path}")
    return write_timeframe_files(symbol, output_folder, df_1min)


def MaterializeTimeframeFiles(symbol: str, output_folder=DEFAULT_DATA_FOLDER):
    return materialize_timeframe_files(symbol, output_folder)


def GoldPaperTrade(symbols=None, **kwargs):
    from Paper import GoldPaperTrade as RunGoldPaperTrade

    if symbols is None:
        symbols = ["CGPOWER"]
    return RunGoldPaperTrade(symbols, **kwargs)


def Strategy(name: str = "G01", **kwargs):
    from Strategies import Strategy as LoadStrategy

    return LoadStrategy(name=name, **kwargs)


def ResolveFyersSymbol(symbol: str) -> str:
    return resolve_fyers_symbol(symbol)


def _symbol_list(symbols) -> list[str]:
    if symbols is None:
        return ["CGPOWER"]
    if isinstance(symbols, str):
        return [symbols.strip().upper()]
    return [str(symbol).strip().upper() for symbol in symbols]


def RunExample(
    action: str = "scan_local",
    symbols: str | list[str] = "CGPOWER",
    *,
    strategyName: str = "G01",
    days: int = 5,
    updateData: bool | None = None,
    refreshDays: int = 120,
    downloadTotalDays: int = 120,
    chunkDays: int = 100,
    downloadStats: bool = True,
    outputFolder=DEFAULT_DATA_FOLDER,
    paperPollSeconds: int = 30,
    paperDurationMinutes: int = 240,
    paperInitialBalance: float = 1000.0,
    paperLeverage: float = 5.0,
    paperReset: bool = False,
    paperManageLiveTick: bool = True,
    mutualFundName: str = _MutualFunds.DEFAULT_FUND,
    mutualFundTimeout: int = 30,
    mutualFundRetries: int = 3,
):
    action = str(action).strip().lower()
    symbols = _symbol_list(symbols)

    if action == "download":
        return Download(
            symbols=symbols,
            output_folder=outputFolder,
            chunk_days=chunkDays,
            total_days=downloadTotalDays,
            downloadStats=downloadStats,
        )

    if action == "mutual_fund":
        return DownloadMutualFund(
            mutualFundName,
            output_folder=outputFolder,
            timeout=mutualFundTimeout,
            retries=mutualFundRetries,
        )

    if action == "materialize":
        return {
            symbol: MaterializeTimeframeFiles(symbol, output_folder=outputFolder)
            for symbol in symbols
        }

    if action == "scan":
        should_update = True if updateData is None else bool(updateData)
        return Strategy(strategyName, data_folder=outputFolder).Scan(
            symbols,
            days=days,
            updateData=should_update,
            refreshDays=refreshDays,
            chunkDays=chunkDays,
            downloadStats=downloadStats,
        )

    if action == "scan_local":
        should_update = False if updateData is None else bool(updateData)
        return Strategy(strategyName, data_folder=outputFolder).Scan(
            symbols,
            days=days,
            updateData=should_update,
            refreshDays=refreshDays,
            chunkDays=chunkDays,
            downloadStats=downloadStats,
        )

    if action == "backtest":
        should_update = False if updateData is None else bool(updateData)
        return Strategy(strategyName, data_folder=outputFolder).Backtest(
            symbols,
            updateData=should_update,
            refreshDays=refreshDays,
            chunkDays=chunkDays,
            downloadStats=downloadStats,
        )

    if action == "paper":
        from Paper.GoldPaperTrader import PaperConfig

        return GoldPaperTrade(
            symbols,
            data_folder=outputFolder,
            poll_seconds=paperPollSeconds,
            duration_minutes=paperDurationMinutes,
            reset=paperReset,
            manage_live_tick=paperManageLiveTick,
            config=PaperConfig(
                initial_balance=paperInitialBalance,
                leverage=paperLeverage,
            ),
        )

    raise ValueError(
        "Unknown ACTION. Use one of: download, mutual_fund, materialize, scan, scan_local, backtest, paper"
    )


def ClearScreen() -> None:
    print("\033[2J\033[H", end="")
