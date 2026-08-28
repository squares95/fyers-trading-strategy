from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

import Download as DataDownload

from . import Core, Gold

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_FOLDER = ROOT / "Data"
DEFAULT_REPORT_FOLDER = ROOT / "Paper" / "Reports" / "Scans"
DEFAULT_REFRESH_DAYS = 120
DEFAULT_CHUNK_DAYS = 100


@dataclass(frozen=True)
class StrategyScanResult:
    strategy: str
    symbols: list[str]
    days: int
    report_path: str
    summary: pd.DataFrame
    trades: pd.DataFrame
    signals: pd.DataFrame


def CleanSymbol(symbol: str) -> str:
    value = str(symbol).strip().upper()
    if ":" in value:
        value = value.split(":", 1)[1]
    return value.replace("-EQ", "")


def SymbolDataPath(symbol: str, data_folder: str | Path = DEFAULT_DATA_FOLDER) -> Path:
    clean = CleanSymbol(symbol)
    return Path(data_folder) / clean / f"{clean}_5MIN.csv"


def LastTradingDates(df: pd.DataFrame, days: int) -> set[str]:
    dates = sorted(str(value) for value in df["date"].dropna().unique())
    if days <= 0 or days >= len(dates):
        return set(dates)
    return set(dates[-days:])


def BuildTrades(
    symbol: str, data_folder: str | Path = DEFAULT_DATA_FOLDER
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    path = SymbolDataPath(symbol, data_folder)
    if not path.exists():
        raise FileNotFoundError(f"Missing 5MIN data for {CleanSymbol(symbol)} at {path}")

    df = Core.prepare_features(path)
    regime = Gold.daily_regime_table(df)
    tradeable_dates = set(regime.loc[regime["regime_tradeable"], "date"])

    signals = Core.generate_signals(df, Gold.GOLD_CONFIG)
    signals = signals[signals["date"].isin(tradeable_dates)].copy()
    strength_signals = Gold.signal_strength_table(df, signals, Gold.GOLD_CONFIG)

    setup_trades = Gold.add_period_columns(Core.backtest(df, signals, Gold.GOLD_CONFIG))
    setup_trades = Gold.attach_signal_strength(setup_trades, strength_signals)
    final_trades = setup_trades[
        (setup_trades["signal_strength"] >= Gold.MIN_SIGNAL_STRENGTH)
        & (setup_trades["strength_trigger_component"] >= Gold.MIN_TRIGGER_COMPONENT)
    ].copy()

    clean = CleanSymbol(symbol)
    for frame in (strength_signals, final_trades):
        if not frame.empty:
            frame.insert(0, "symbol", clean)
    if not final_trades.empty:
        final_trades["side"] = final_trades["direction"].map({1: "Long", -1: "Short"})
        final_trades["net_return_pct"] = (final_trades["net_return"].astype(float) * 100).round(3)
    return df, strength_signals, final_trades


def SummarizeTrades(
    symbol: str, df: pd.DataFrame, trades: pd.DataFrame, selected_dates: set[str]
) -> dict[str, object]:
    filtered = trades[trades["date"].isin(selected_dates)].copy() if not trades.empty else trades
    stats = Gold.equity_stats(filtered)
    return {
        "symbol": CleanSymbol(symbol),
        "scan_days": len(selected_dates),
        "date_start": min(selected_dates) if selected_dates else "",
        "date_end": max(selected_dates) if selected_dates else "",
        "data_rows": len(df),
        **stats,
    }


def SaveScanReport(
    result: StrategyScanResult, report_folder: str | Path = DEFAULT_REPORT_FOLDER
) -> Path:
    folder = Path(report_folder)
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = folder / f"{result.strategy}_Scan_{timestamp}.xlsx"

    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            result.summary.to_excel(writer, sheet_name="Summary", index=False)
            result.trades.to_excel(writer, sheet_name="Trades", index=False)
            result.signals.to_excel(writer, sheet_name="Signals", index=False)
    except PermissionError:
        path = path.with_name(f"{path.stem}_live{path.suffix}")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            result.summary.to_excel(writer, sheet_name="Summary", index=False)
            result.trades.to_excel(writer, sheet_name="Trades", index=False)
            result.signals.to_excel(writer, sheet_name="Signals", index=False)
    return path


class G01Strategy:
    name = "G01"

    def __init__(
        self,
        *,
        data_folder: str | Path = DEFAULT_DATA_FOLDER,
        report_folder: str | Path = DEFAULT_REPORT_FOLDER,
        updateData: bool = True,
        refreshDays: int = DEFAULT_REFRESH_DAYS,
        chunkDays: int = DEFAULT_CHUNK_DAYS,
        downloadStats: bool = False,
    ) -> None:
        self.data_folder = Path(data_folder)
        self.report_folder = Path(report_folder)
        self.updateData = bool(updateData)
        self.refreshDays = int(refreshDays)
        self.chunkDays = int(chunkDays)
        self.downloadStats = bool(downloadStats)

    def RefreshData(
        self,
        symbols: Iterable[str],
        *,
        days: int = 5,
        updateData: bool | None = None,
        refreshDays: int | None = None,
        chunkDays: int | None = None,
        downloadStats: bool | None = None,
    ) -> bool:
        should_update = self.updateData if updateData is None else bool(updateData)
        if not should_update:
            return False

        scan_days = max(1, int(days)) if int(days) > 0 else 1
        refresh_window = max(
            scan_days, int(refreshDays if refreshDays is not None else self.refreshDays)
        )
        DataDownload.Download(
            list(symbols),
            output_folder=str(self.data_folder),
            chunk_days=int(chunkDays if chunkDays is not None else self.chunkDays),
            total_days=refresh_window,
            downloadStats=self.downloadStats if downloadStats is None else bool(downloadStats),
        )
        return True

    def Scan(
        self,
        symbols: Iterable[str] | None = None,
        days: int = 5,
        *,
        updateData: bool | None = None,
        refreshDays: int | None = None,
        chunkDays: int | None = None,
        downloadStats: bool | None = None,
    ) -> StrategyScanResult:
        clean_symbols = [CleanSymbol(symbol) for symbol in (symbols or ["CGPOWER"])]
        self.RefreshData(
            clean_symbols,
            days=int(days),
            updateData=updateData,
            refreshDays=refreshDays,
            chunkDays=chunkDays,
            downloadStats=downloadStats,
        )
        all_summary = []
        all_trades = []
        all_signals = []

        for symbol in clean_symbols:
            df, signals, trades = BuildTrades(symbol, self.data_folder)
            selected_dates = LastTradingDates(df, int(days))
            scan_signals = (
                signals[signals["date"].isin(selected_dates)].copy()
                if not signals.empty
                else signals
            )
            scan_trades = (
                trades[trades["date"].isin(selected_dates)].copy() if not trades.empty else trades
            )
            all_summary.append(SummarizeTrades(symbol, df, trades, selected_dates))
            all_signals.append(scan_signals)
            all_trades.append(scan_trades)

        summary = pd.DataFrame(all_summary)
        trades_out = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
        signals_out = pd.concat(all_signals, ignore_index=True) if all_signals else pd.DataFrame()
        result = StrategyScanResult(
            strategy=self.name,
            symbols=clean_symbols,
            days=int(days),
            report_path="",
            summary=summary,
            trades=trades_out,
            signals=signals_out,
        )
        report_path = SaveScanReport(result, self.report_folder)
        result = StrategyScanResult(
            strategy=result.strategy,
            symbols=result.symbols,
            days=result.days,
            report_path=str(report_path),
            summary=result.summary,
            trades=result.trades,
            signals=result.signals,
        )
        self.PrintScan(result)
        return result

    def Backtest(
        self,
        symbols: Iterable[str] | None = None,
        *,
        updateData: bool | None = None,
        refreshDays: int | None = None,
        chunkDays: int | None = None,
        downloadStats: bool | None = None,
    ) -> StrategyScanResult:
        return self.Scan(
            symbols=symbols,
            days=0,
            updateData=updateData,
            refreshDays=refreshDays,
            chunkDays=chunkDays,
            downloadStats=downloadStats,
        )

    def PaperTrade(self, symbols: Iterable[str] | None = None, **kwargs):
        from Paper import GoldPaperTrade

        return GoldPaperTrade(list(symbols or ["CGPOWER"]), **kwargs)

    def PrintScan(self, result: StrategyScanResult) -> None:
        print(f"{result.strategy} scan complete. Report: {result.report_path}")
        if result.summary.empty:
            print("No symbols scanned.")
            return
        for row in result.summary.itertuples(index=False):
            print(
                f"{row.symbol}: days={row.scan_days}, trades={row.trades}, "
                f"net={row.net_pct}%, win={row.win_rate_pct}%, pf={row.profit_factor}"
            )
        if result.trades.empty:
            print("No matching trades/signals in the selected window.")
            return
        display_cols = [
            "symbol",
            "side",
            "signal_time",
            "entry_time",
            "entry",
            "exit_time",
            "exit",
            "exit_reason",
            "signal_strength",
            "net_return_pct",
        ]
        print(
            result.trades[[col for col in display_cols if col in result.trades.columns]].to_string(
                index=False
            )
        )
