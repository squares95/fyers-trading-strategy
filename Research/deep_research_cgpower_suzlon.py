from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Strategies.G01 import Core as base
from Strategies.G01 import Gold as gold


DATA_DIR = ROOT / "Data"
SLIM_DIR = ROOT / "Data" / "_slim"
OUTPUT_DIR = ROOT / "Research"
SYMBOLS = ["CGPOWER", "SUZLON"]


def _resolve_data_path(symbol: str, timeframe: str) -> Path:
    """Prefer slim bundle, fall back to full Data/."""
    slim = SLIM_DIR / f"{symbol}_{timeframe}.csv"
    if slim.exists():
        return slim
    return DATA_DIR / symbol / f"{symbol}_{timeframe}.csv"


EVENTS = {
    "CGPOWER": [
        ("2021-10-21", "Q2 FY22 turnaround confirmation"),
        ("2023-05-08", "Q4 FY23 growth confirmation"),
        ("2024-02-29", "Semiconductor ATMP unit approved"),
        ("2024-10-05", "RF components acquisition from Renesas"),
        ("2025-05-06", "Q4 FY25 strong order backlog"),
        ("2026-01-17", "Rs 900 Cr Tallgrass US data-center transformer order"),
        ("2026-05-06", "Q4 FY26 order backlog expansion"),
    ],
    "SUZLON": [
        ("2023-11-02", "Q2 FY24 net-debt-free balance sheet"),
        ("2024-05-24", "Q4 FY24 largest-ever order book"),
        ("2024-09-09", "NTPC Green 1,166 MW order"),
        ("2025-05-29", "FY25 best year in a decade"),
        ("2025-09-16", "Tata Power Renewable 838 MW order"),
        ("2026-02-05", "Q3 FY26 record order book"),
        ("2026-05-25", "Q4 FY26 robust annual performance"),
    ],
}


def load_timeframe(symbol: str, timeframe: str) -> pd.DataFrame:
    path = _resolve_data_path(symbol, timeframe)
    df = pd.read_csv(path, parse_dates=["Datetime"])
    df = df.sort_values("Datetime").reset_index(drop=True)
    df["date"] = df["Datetime"].dt.date.astype(str)
    return df


def complete_dates_from_1min(df_1m: pd.DataFrame) -> set[str]:
    market = df_1m[
        (df_1m["Datetime"].dt.strftime("%H:%M") >= "09:15")
        & (df_1m["Datetime"].dt.strftime("%H:%M") <= "15:29")
    ].copy()
    counts = market.groupby("date").size()
    return set(counts[counts == 375].index)


def max_drawdown(close: pd.Series) -> float:
    equity = close.astype(float) / float(close.iloc[0])
    dd = equity / equity.cummax() - 1
    return float(dd.min())


def make_daily_features(symbol: str) -> pd.DataFrame:
    df_1m = load_timeframe(symbol, "1MIN")
    complete_dates = complete_dates_from_1min(df_1m)
    daily = load_timeframe(symbol, "1D")
    daily = daily[daily["date"].isin(complete_dates)].copy().reset_index(drop=True)
    daily["prev_close"] = daily["Close"].shift(1)
    daily["ret"] = daily["Close"].pct_change()
    daily["intraday_ret"] = daily["Close"] / daily["Open"] - 1
    daily["gap_pct"] = daily["Open"] / daily["prev_close"] - 1
    daily["range_pct"] = (daily["High"] - daily["Low"]) / daily["prev_close"]
    daily["close_pos"] = (daily["Close"] - daily["Low"]) / (daily["High"] - daily["Low"]).replace(0, np.nan)
    daily["turnover"] = daily["Close"] * daily["Volume"]
    daily["vol_med20_prev"] = daily["Volume"].rolling(20, min_periods=10).median().shift(1)
    daily["vol_ratio20"] = daily["Volume"] / daily["vol_med20_prev"]
    for window in [10, 20, 50, 100, 200]:
        daily[f"sma{window}"] = daily["Close"].rolling(window, min_periods=max(5, window // 2)).mean()
    for window in [5, 20, 60, 120]:
        daily[f"ret_{window}d"] = daily["Close"] / daily["Close"].shift(window) - 1
    daily["trend_quality"] = 0
    daily.loc[daily["Close"] > daily["sma50"], "trend_quality"] += 1
    daily.loc[daily["sma50"] > daily["sma200"], "trend_quality"] += 1
    daily.loc[daily["ret_60d"] > 0, "trend_quality"] += 1
    daily.loc[daily["vol_ratio20"] > 1.2, "trend_quality"] += 1
    daily["regime"] = np.select(
        [
            (daily["trend_quality"] >= 3) & (daily["ret_20d"] > 0),
            (daily["Close"] > daily["sma200"]) & (daily["ret_20d"] <= 0),
            (daily["Close"] < daily["sma50"]) & (daily["ret_60d"] < 0),
        ],
        ["bull_expansion", "bull_pullback", "derisk_downtrend"],
        default="mixed_chop",
    )
    return daily


def make_weekly_features(daily: pd.DataFrame) -> pd.DataFrame:
    temp = daily.copy()
    temp["_week"] = temp["Datetime"].dt.to_period("W-FRI")
    weekly = (
        temp.groupby("_week", sort=True)
        .agg(
            week_start=("Datetime", "first"),
            week_end=("Datetime", "last"),
            days=("date", "count"),
            Open=("Open", "first"),
            High=("High", "max"),
            Low=("Low", "min"),
            Close=("Close", "last"),
            Volume=("Volume", "sum"),
            up_days=("ret", lambda s: int((s > 0).sum())),
        )
        .reset_index(drop=True)
    )
    weekly["ret"] = weekly["Close"] / weekly["Open"] - 1
    weekly["close_pos"] = (weekly["Close"] - weekly["Low"]) / (weekly["High"] - weekly["Low"]).replace(0, np.nan)
    weekly["vol_ratio20"] = weekly["Volume"] / weekly["Volume"].rolling(20, min_periods=8).median().shift(1)
    weekly["ret_8w"] = weekly["Close"] / weekly["Close"].shift(8) - 1
    weekly["sma10"] = weekly["Close"].rolling(10, min_periods=5).mean()
    weekly["sma30"] = weekly["Close"].rolling(30, min_periods=10).mean()
    weekly["weekly_bull"] = (weekly["Close"] > weekly["sma10"]) & (weekly["sma10"] > weekly["sma30"])
    return weekly


def summarize_daily(symbol: str, daily: pd.DataFrame) -> dict[str, object]:
    first = daily.iloc[0]
    last = daily.iloc[-1]
    years = (last["Datetime"] - first["Datetime"]).days / 365.25
    total_return = float(last["Close"] / first["Close"] - 1)
    cagr = float((last["Close"] / first["Close"]) ** (1 / years) - 1) if years > 0 else np.nan
    return {
        "symbol": symbol,
        "days": int(len(daily)),
        "start": str(first["Datetime"]),
        "end": str(last["Datetime"]),
        "first_close": round(float(first["Close"]), 2),
        "last_close": round(float(last["Close"]), 2),
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "max_drawdown_pct": round(max_drawdown(daily["Close"]) * 100, 2),
        "median_daily_range_pct": round(float(daily["range_pct"].median() * 100), 2),
        "median_turnover_cr": round(float(daily["turnover"].median() / 10_000_000), 2),
        "up_day_pct": round(float((daily["ret"] > 0).mean() * 100), 2),
        "bull_expansion_days": int((daily["regime"] == "bull_expansion").sum()),
        "derisk_downtrend_days": int((daily["regime"] == "derisk_downtrend").sum()),
    }


def top_table(daily: pd.DataFrame, symbol: str, direction: int, n: int = 12) -> pd.DataFrame:
    cols = [
        "date",
        "Open",
        "High",
        "Low",
        "Close",
        "ret",
        "intraday_ret",
        "gap_pct",
        "range_pct",
        "close_pos",
        "vol_ratio20",
        "regime",
    ]
    out = daily[cols].copy()
    out["symbol"] = symbol
    sort_col = "ret"
    out = out.sort_values(sort_col, ascending=(direction < 0)).head(n)
    for col in ["ret", "intraday_ret", "gap_pct", "range_pct", "close_pos", "vol_ratio20"]:
        out[col] = out[col].astype(float).round(4)
    return out[["symbol"] + cols]


def top_weeks(weekly: pd.DataFrame, symbol: str, n: int = 10) -> pd.DataFrame:
    cols = ["week_start", "week_end", "days", "Open", "High", "Low", "Close", "ret", "up_days", "close_pos", "vol_ratio20", "weekly_bull"]
    out = weekly[cols].sort_values("ret", ascending=False).head(n).copy()
    out["symbol"] = symbol
    for col in ["ret", "close_pos", "vol_ratio20"]:
        out[col] = out[col].astype(float).round(4)
    return out[["symbol"] + cols]


def intraday_profile(symbol: str, daily: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
    df = load_timeframe(symbol, "1MIN")
    complete_dates = set(daily["date"])
    df = df[df["date"].isin(complete_dates)].copy()
    profiles = []
    for date_key, g in df.groupby("date", sort=True):
        if len(g) < 375:
            continue
        g = g.sort_values("Datetime").reset_index(drop=True)
        open_px = float(g.at[0, "Open"])
        close_px = float(g.at[len(g) - 1, "Close"])
        first30 = g.iloc[:30]
        after30 = g.iloc[30:]
        orh = float(first30["High"].max())
        orl = float(first30["Low"].min())
        close30 = float(first30.iloc[-1]["Close"])
        up_break = after30[after30["High"] > orh]
        down_break = after30[after30["Low"] < orl]
        up_price = float(up_break.iloc[0]["High"]) if not up_break.empty else np.nan
        down_price = float(down_break.iloc[0]["Low"]) if not down_break.empty else np.nan
        profiles.append(
            {
                "symbol": symbol,
                "date": date_key,
                "first30_ret": close30 / open_px - 1,
                "day_ret": close_px / open_px - 1,
                "opening_range_pct": (orh - orl) / open_px,
                "orb_up": bool(not up_break.empty),
                "orb_up_success": bool(close_px > up_price) if not up_break.empty else False,
                "orb_up_close_ret": close_px / up_price - 1 if not up_break.empty else np.nan,
                "orb_down": bool(not down_break.empty),
                "orb_down_success": bool(close_px < down_price) if not down_break.empty else False,
                "orb_down_close_ret": down_price / close_px - 1 if not down_break.empty else np.nan,
            }
        )
    intraday = pd.DataFrame(profiles)
    merged = intraday.merge(daily[["date", "ret", "vol_ratio20", "regime"]], on="date", how="left", suffixes=("", "_daily"))
    strong_up = merged[(merged["ret"] >= 0.03) & (merged["vol_ratio20"] >= 1.2)]
    strong_down = merged[(merged["ret"] <= -0.03) & (merged["vol_ratio20"] >= 1.2)]
    bull = merged[merged["regime"] == "bull_expansion"]
    summary = {
        "symbol": symbol,
        "days": int(len(merged)),
        "avg_first30_ret_bps": round(float(merged["first30_ret"].mean() * 10000), 2),
        "first30_predicts_positive_day_pct": round(float((merged[merged["first30_ret"] > 0]["day_ret"] > 0).mean() * 100), 2),
        "orb_up_days": int(merged["orb_up"].sum()),
        "orb_up_success_pct": round(float(merged.loc[merged["orb_up"], "orb_up_success"].mean() * 100), 2),
        "orb_up_avg_close_bps": round(float(merged.loc[merged["orb_up"], "orb_up_close_ret"].mean() * 10000), 2),
        "orb_down_days": int(merged["orb_down"].sum()),
        "orb_down_success_pct": round(float(merged.loc[merged["orb_down"], "orb_down_success"].mean() * 100), 2),
        "orb_down_avg_close_bps": round(float(merged.loc[merged["orb_down"], "orb_down_close_ret"].mean() * 10000), 2),
        "bull_regime_orb_up_success_pct": round(float(bull.loc[bull["orb_up"], "orb_up_success"].mean() * 100), 2) if not bull.empty else 0.0,
        "strong_up_days": int(len(strong_up)),
        "strong_up_avg_first30_bps": round(float(strong_up["first30_ret"].mean() * 10000), 2) if not strong_up.empty else 0.0,
        "strong_up_orb_up_success_pct": round(float(strong_up.loc[strong_up["orb_up"], "orb_up_success"].mean() * 100), 2) if not strong_up.empty else 0.0,
        "strong_down_days": int(len(strong_down)),
        "strong_down_avg_first30_bps": round(float(strong_down["first30_ret"].mean() * 10000), 2) if not strong_down.empty else 0.0,
        "strong_down_orb_down_success_pct": round(float(strong_down.loc[strong_down["orb_down"], "orb_down_success"].mean() * 100), 2) if not strong_down.empty else 0.0,
    }
    return summary, merged


def event_window_table(symbol: str, daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dates = pd.to_datetime(daily["date"])
    for event_date, event_name in EVENTS[symbol]:
        event_ts = pd.Timestamp(event_date)
        idx_candidates = np.where(dates >= event_ts)[0]
        if len(idx_candidates) == 0:
            continue
        idx = int(idx_candidates[0])
        pre_start = max(0, idx - 20)
        post_end = min(len(daily) - 1, idx + 20)
        event_close = float(daily.iloc[idx]["Close"])
        pre_close = float(daily.iloc[pre_start]["Close"])
        post_close = float(daily.iloc[post_end]["Close"])
        rows.append(
            {
                "symbol": symbol,
                "event_date": event_date,
                "trading_date_used": daily.iloc[idx]["date"],
                "event": event_name,
                "pre_20d_pct": round((event_close / pre_close - 1) * 100, 2),
                "post_20d_pct": round((post_close / event_close - 1) * 100, 2),
                "event_day_ret_pct": round(float(daily.iloc[idx]["ret"] * 100), 2),
                "event_day_vol_ratio": round(float(daily.iloc[idx]["vol_ratio20"]), 2),
                "regime": daily.iloc[idx]["regime"],
            }
        )
    return pd.DataFrame(rows)


def strategy_summary(symbol: str) -> dict[str, object]:
    path = _resolve_data_path(symbol, "5MIN")
    df = base.prepare_features(path)
    regime = gold.daily_regime_table(df)
    tradeable_dates = set(regime.loc[regime["regime_tradeable"], "date"])
    all_signals = base.generate_signals(df, gold.GOLD_CONFIG)
    regime_signals = all_signals[all_signals["date"].isin(tradeable_dates)].copy()
    strength = gold.signal_strength_table(df, regime_signals, gold.GOLD_CONFIG)
    trades = gold.add_period_columns(base.backtest(df, regime_signals, gold.GOLD_CONFIG))
    trades = gold.attach_signal_strength(trades, strength)
    final = trades[
        (trades["signal_strength"] >= gold.MIN_SIGNAL_STRENGTH)
        & (trades["strength_trigger_component"] >= gold.MIN_TRIGGER_COMPONENT)
    ].copy()
    by_side = {
        "long": gold.equity_stats(final[final["direction"] == 1]),
        "short": gold.equity_stats(final[final["direction"] == -1]),
    }
    return {
        "symbol": symbol,
        "signals_before_regime": int(len(all_signals)),
        "signals_after_regime": int(len(regime_signals)),
        "final": gold.equity_stats(final),
        "by_side": by_side,
        "strength_bands": gold.strength_band_stats(final).to_dict(orient="records"),
    }


def run() -> dict[str, object]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    symbol_summaries = []
    intraday_summaries = []
    strategy_summaries = []
    all_top_days = []
    all_bottom_days = []
    all_top_weeks = []
    all_events = []
    all_intraday = []

    result = {"symbols": {}}
    for symbol in SYMBOLS:
        daily = make_daily_features(symbol)
        weekly = make_weekly_features(daily)
        intraday_summary, intraday_rows = intraday_profile(symbol, daily)
        strat = strategy_summary(symbol)
        daily_summary = summarize_daily(symbol, daily)

        symbol_summaries.append(daily_summary)
        intraday_summaries.append(intraday_summary)
        strategy_summaries.append(strat)
        all_top_days.append(top_table(daily, symbol, 1))
        all_bottom_days.append(top_table(daily, symbol, -1))
        all_top_weeks.append(top_weeks(weekly, symbol))
        all_events.append(event_window_table(symbol, daily))
        all_intraday.append(intraday_rows)

        result["symbols"][symbol] = {
            "daily_summary": daily_summary,
            "intraday_summary": intraday_summary,
            "strategy_summary": strat,
            "regime_counts": daily["regime"].value_counts().to_dict(),
        }

    pd.DataFrame(symbol_summaries).to_csv(OUTPUT_DIR / "deep_research_symbol_summary.csv", index=False)
    pd.DataFrame(intraday_summaries).to_csv(OUTPUT_DIR / "deep_research_intraday_summary.csv", index=False)
    pd.DataFrame(strategy_summaries).to_csv(OUTPUT_DIR / "deep_research_strategy_summary.csv", index=False)
    pd.concat(all_top_days).to_csv(OUTPUT_DIR / "deep_research_top_up_days.csv", index=False)
    pd.concat(all_bottom_days).to_csv(OUTPUT_DIR / "deep_research_top_down_days.csv", index=False)
    pd.concat(all_top_weeks).to_csv(OUTPUT_DIR / "deep_research_top_weeks.csv", index=False)
    pd.concat(all_events).to_csv(OUTPUT_DIR / "deep_research_event_windows.csv", index=False)
    pd.concat(all_intraday).to_csv(OUTPUT_DIR / "deep_research_intraday_days.csv", index=False)
    (OUTPUT_DIR / "deep_research_cgpower_suzlon_summary.json").write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
