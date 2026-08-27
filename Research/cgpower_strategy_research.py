from __future__ import annotations

import itertools
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "Data" / "NSE30" / "CGPOWER.csv"
OUTPUT_DIR = ROOT / "Research"

MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:25"
COST_BPS_PER_SIDE = 5.0


@dataclass(frozen=True)
class Trade:
    strategy: str
    variant: str
    direction: int
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    gross_return: float
    net_return: float
    r_multiple: float
    exit_reason: str
    date: str


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    return pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def add_adx(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series]:
    up_move = df["High"].diff()
    down_move = -df["Low"].diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index
    )
    atr = true_range(df).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return atr, adx


def load_data() -> pd.DataFrame:
    raw = pd.read_csv(DATA_PATH, parse_dates=["Datetime"])
    raw = raw.sort_values("Datetime").reset_index(drop=True)
    raw["date"] = raw["Datetime"].dt.date.astype(str)
    raw["time"] = raw["Datetime"].dt.strftime("%H:%M")

    regular = raw[(raw["time"] >= MARKET_OPEN) & (raw["time"] <= MARKET_CLOSE)].copy()
    day_counts = regular.groupby("date").size()
    regular_days = day_counts[day_counts == 75].index
    df = regular[regular["date"].isin(regular_days)].copy().reset_index(drop=True)
    df["bar_no"] = df.groupby("date").cumcount()
    df["is_first_bar"] = df["bar_no"].eq(0)
    df["is_last_bar"] = df["bar_no"].eq(74)

    daily = (
        df.groupby("date")
        .agg(
            day_open=("Open", "first"),
            day_high=("High", "max"),
            day_low=("Low", "min"),
            day_close=("Close", "last"),
            day_volume=("Volume", "sum"),
        )
        .reset_index()
    )
    daily["prev_close"] = daily["day_close"].shift(1)
    daily["prev_high"] = daily["day_high"].shift(1)
    daily["prev_low"] = daily["day_low"].shift(1)
    daily["daily_ema20_prev"] = ema(daily["day_close"], 20).shift(1)
    daily["daily_ema50_prev"] = ema(daily["day_close"], 50).shift(1)
    daily["daily_trend_up"] = daily["daily_ema20_prev"] > daily["daily_ema50_prev"]
    daily["daily_trend_down"] = daily["daily_ema20_prev"] < daily["daily_ema50_prev"]
    daily["gap_pct"] = daily["day_open"] / daily["prev_close"] - 1
    df = df.merge(
        daily[
            [
                "date",
                "prev_close",
                "prev_high",
                "prev_low",
                "daily_ema20_prev",
                "daily_ema50_prev",
                "daily_trend_up",
                "daily_trend_down",
                "gap_pct",
            ]
        ],
        on="date",
        how="left",
    )

    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    df["vwap"] = (typical * df["Volume"]).groupby(df["date"]).cumsum() / df["Volume"].groupby(
        df["date"]
    ).cumsum()

    for span in [5, 8, 9, 13, 21, 34, 55, 89]:
        df[f"ema{span}"] = ema(df["Close"], span)

    df["rsi14"] = rsi(df["Close"], 14)
    df["atr14_calc"], df["adx14_calc"] = add_adx(df, 14)
    df["atr21_calc"], df["adx21_calc"] = add_adx(df, 21)

    # Same-bar-of-day volume ratio prevents the open/close volume smile from
    # looking like a false volume spike.
    df["vol_avg20_samebar"] = df.groupby("bar_no")["Volume"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=5).mean()
    )
    df["vol_ratio20"] = df["Volume"] / df["vol_avg20_samebar"]

    df["range_pct"] = (df["High"] - df["Low"]) / df["Open"]
    df["body_pct_of_range"] = (df["Close"] - df["Open"]).abs() / (
        df["High"] - df["Low"]
    ).replace(0, np.nan)

    for n in [10, 15, 20, 30, 40]:
        df[f"donch_hi_{n}"] = df["High"].shift(1).rolling(n, min_periods=n).max()
        df[f"donch_lo_{n}"] = df["Low"].shift(1).rolling(n, min_periods=n).min()

    for n in [3, 6, 9]:
        df[f"or_hi_{n}"] = df.groupby("date")["High"].transform(lambda s: s.iloc[:n].max())
        df[f"or_lo_{n}"] = df.groupby("date")["Low"].transform(lambda s: s.iloc[:n].min())

    return df


def simulate_trade(
    day: pd.DataFrame,
    signal_pos: int,
    direction: int,
    strategy: str,
    variant: str,
    stop_distance: float,
    target_r: float,
    trail_atr_mult: float | None = None,
    max_hold_bars: int | None = None,
    cost_bps_per_side: float = COST_BPS_PER_SIDE,
) -> Trade | None:
    entry_pos = signal_pos + 1
    if entry_pos >= len(day) or day.iloc[entry_pos]["is_last_bar"]:
        return None

    entry_bar = day.iloc[entry_pos]
    entry = float(entry_bar["Open"])
    if not np.isfinite(stop_distance) or stop_distance <= 0:
        return None

    stop = entry - direction * stop_distance
    target = entry + direction * target_r * stop_distance
    best = entry
    final_pos = len(day) - 1
    if max_hold_bars is not None:
        final_pos = min(final_pos, entry_pos + max_hold_bars)

    exit_price = float(day.iloc[final_pos]["Close"])
    exit_pos = final_pos
    exit_reason = "eod" if final_pos == len(day) - 1 else "timeout"

    for pos in range(entry_pos, final_pos + 1):
        row = day.iloc[pos]
        high = float(row["High"])
        low = float(row["Low"])

        if trail_atr_mult is not None:
            atr = float(row["atr14_calc"])
            if direction == 1:
                best = max(best, high)
                stop = max(stop, best - trail_atr_mult * atr)
            else:
                best = min(best, low)
                stop = min(stop, best + trail_atr_mult * atr)

        if direction == 1:
            stop_hit = low <= stop
            target_hit = high >= target
            if stop_hit and target_hit:
                exit_price, exit_reason, exit_pos = stop, "stop_same_bar", pos
                break
            if stop_hit:
                exit_price, exit_reason, exit_pos = stop, "stop", pos
                break
            if target_hit:
                exit_price, exit_reason, exit_pos = target, "target", pos
                break
        else:
            stop_hit = high >= stop
            target_hit = low <= target
            if stop_hit and target_hit:
                exit_price, exit_reason, exit_pos = stop, "stop_same_bar", pos
                break
            if stop_hit:
                exit_price, exit_reason, exit_pos = stop, "stop", pos
                break
            if target_hit:
                exit_price, exit_reason, exit_pos = target, "target", pos
                break

    gross = direction * (exit_price / entry - 1)
    net = gross - (2 * cost_bps_per_side / 10000)
    return Trade(
        strategy=strategy,
        variant=variant,
        direction=direction,
        entry_time=str(entry_bar["Datetime"]),
        exit_time=str(day.iloc[exit_pos]["Datetime"]),
        entry=entry,
        exit=exit_price,
        gross_return=gross,
        net_return=net,
        r_multiple=direction * (exit_price - entry) / stop_distance,
        exit_reason=exit_reason,
        date=str(entry_bar["date"]),
    )


def backtest_daily_signals(
    day_frames: list[tuple[str, pd.DataFrame]],
    strategy: str,
    variant: str,
    signal_fn: Callable[[pd.DataFrame], Iterable[tuple[int, int, float]]],
    target_r: float,
    trail_atr_mult: float | None = None,
    max_trades_per_day: int = 1,
    max_hold_bars: int | None = None,
) -> list[Trade]:
    trades: list[Trade] = []
    for _, day in day_frames:
        taken = 0
        for signal_pos, direction, stop_distance in signal_fn(day):
            trade = simulate_trade(
                day,
                signal_pos,
                direction,
                strategy,
                variant,
                stop_distance,
                target_r,
                trail_atr_mult=trail_atr_mult,
                max_hold_bars=max_hold_bars,
            )
            if trade is not None:
                trades.append(trade)
                taken += 1
            if taken >= max_trades_per_day:
                break
    return trades


def opening_range_signal_fn(
    or_bars: int,
    side: str,
    ema_fast: int,
    ema_slow: int,
    adx_min: float,
    vol_min: float,
    stop_atr: float,
    latest_signal_bar: int,
    use_daily_trend: bool,
) -> Callable[[pd.DataFrame], Iterable[tuple[int, int, float]]]:
    def signals(day: pd.DataFrame) -> Iterable[tuple[int, int, float]]:
        if len(day) < 75:
            return
        or_slice = day.iloc[:or_bars]
        or_high = float(or_slice["High"].max())
        or_low = float(or_slice["Low"].min())
        for pos in range(or_bars, min(latest_signal_bar, len(day) - 2)):
            row = day.iloc[pos]
            if not np.isfinite(row["vol_ratio20"]):
                continue
            atr = float(row["atr14_calc"])
            stop_distance = stop_atr * atr
            if side in ("long", "both"):
                if (
                    row["Close"] > or_high
                    and row["Close"] > row["vwap"]
                    and row[f"ema{ema_fast}"] > row[f"ema{ema_slow}"]
                    and row["ADX"] >= adx_min
                    and row["vol_ratio20"] >= vol_min
                    and (not use_daily_trend or bool(row["daily_trend_up"]))
                ):
                    yield pos, 1, stop_distance
                    return
            if side in ("short", "both"):
                if (
                    row["Close"] < or_low
                    and row["Close"] < row["vwap"]
                    and row[f"ema{ema_fast}"] < row[f"ema{ema_slow}"]
                    and row["ADX"] >= adx_min
                    and row["vol_ratio20"] >= vol_min
                    and (not use_daily_trend or bool(row["daily_trend_down"]))
                ):
                    yield pos, -1, stop_distance
                    return

    return signals


def donchian_signal_fn(
    lookback: int,
    side: str,
    ema_fast: int,
    ema_slow: int,
    adx_min: float,
    vol_min: float,
    stop_atr: float,
    earliest_bar: int,
    latest_signal_bar: int,
    use_prev_day_filter: bool,
) -> Callable[[pd.DataFrame], Iterable[tuple[int, int, float]]]:
    hi_col = f"donch_hi_{lookback}"
    lo_col = f"donch_lo_{lookback}"

    def signals(day: pd.DataFrame) -> Iterable[tuple[int, int, float]]:
        for pos in range(earliest_bar, min(latest_signal_bar, len(day) - 2)):
            row = day.iloc[pos]
            if not np.isfinite(row["vol_ratio20"]):
                continue
            atr = float(row["atr14_calc"])
            stop_distance = stop_atr * atr
            if side in ("long", "both"):
                prev_day_ok = (not use_prev_day_filter) or row["Close"] > row["prev_high"]
                if (
                    row["Close"] > row[hi_col]
                    and row["Close"] > row["vwap"]
                    and row[f"ema{ema_fast}"] > row[f"ema{ema_slow}"]
                    and row["ADX"] >= adx_min
                    and row["vol_ratio20"] >= vol_min
                    and prev_day_ok
                ):
                    yield pos, 1, stop_distance
                    return
            if side in ("short", "both"):
                prev_day_ok = (not use_prev_day_filter) or row["Close"] < row["prev_low"]
                if (
                    row["Close"] < row[lo_col]
                    and row["Close"] < row["vwap"]
                    and row[f"ema{ema_fast}"] < row[f"ema{ema_slow}"]
                    and row["ADX"] >= adx_min
                    and row["vol_ratio20"] >= vol_min
                    and prev_day_ok
                ):
                    yield pos, -1, stop_distance
                    return

    return signals


def pullback_signal_fn(
    side: str,
    ema_fast: int,
    ema_slow: int,
    adx_min: float,
    vol_min: float,
    stop_atr: float,
    earliest_bar: int,
    latest_signal_bar: int,
    rsi_low: float,
    rsi_high: float,
) -> Callable[[pd.DataFrame], Iterable[tuple[int, int, float]]]:
    def signals(day: pd.DataFrame) -> Iterable[tuple[int, int, float]]:
        for pos in range(max(earliest_bar, 2), min(latest_signal_bar, len(day) - 2)):
            row = day.iloc[pos]
            prev = day.iloc[pos - 1]
            if not np.isfinite(row["vol_ratio20"]):
                continue
            atr = float(row["atr14_calc"])
            stop_distance = stop_atr * atr
            if side in ("long", "both"):
                touched = row["Low"] <= row[f"ema{ema_fast}"] or row["Low"] <= row["vwap"]
                recovered = row["Close"] > row[f"ema{ema_fast}"] and row["Close"] > prev["Close"]
                if (
                    row["Close"] > row["vwap"]
                    and row[f"ema{ema_fast}"] > row[f"ema{ema_slow}"]
                    and row["ADX"] >= adx_min
                    and row["vol_ratio20"] >= vol_min
                    and rsi_low <= row["rsi14"] <= rsi_high
                    and touched
                    and recovered
                ):
                    yield pos, 1, stop_distance
                    return
            if side in ("short", "both"):
                touched = row["High"] >= row[f"ema{ema_fast}"] or row["High"] >= row["vwap"]
                recovered = row["Close"] < row[f"ema{ema_fast}"] and row["Close"] < prev["Close"]
                if (
                    row["Close"] < row["vwap"]
                    and row[f"ema{ema_fast}"] < row[f"ema{ema_slow}"]
                    and row["ADX"] >= adx_min
                    and row["vol_ratio20"] >= vol_min
                    and 100 - rsi_high <= row["rsi14"] <= 100 - rsi_low
                    and touched
                    and recovered
                ):
                    yield pos, -1, stop_distance
                    return

    return signals


def vwap_reversion_signal_fn(
    side: str,
    band_atr: float,
    rsi_extreme: float,
    stop_atr: float,
    earliest_bar: int,
    latest_signal_bar: int,
) -> Callable[[pd.DataFrame], Iterable[tuple[int, int, float]]]:
    def signals(day: pd.DataFrame) -> Iterable[tuple[int, int, float]]:
        for pos in range(earliest_bar, min(latest_signal_bar, len(day) - 2)):
            row = day.iloc[pos]
            atr = float(row["atr14_calc"])
            stop_distance = stop_atr * atr
            if side in ("long", "both"):
                if row["Close"] < row["vwap"] - band_atr * atr and row["rsi14"] <= rsi_extreme:
                    yield pos, 1, stop_distance
                    return
            if side in ("short", "both"):
                if row["Close"] > row["vwap"] + band_atr * atr and row["rsi14"] >= 100 - rsi_extreme:
                    yield pos, -1, stop_distance
                    return

    return signals


def equity_drawdown(returns: pd.Series) -> tuple[float, float]:
    if returns.empty:
        return 0.0, 0.0
    equity = (1 + returns).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1
    return float(equity.iloc[-1] - 1), float(dd.min())


def summarize_trades(
    trades: list[Trade],
    train_end_date: str,
    label: str,
) -> dict[str, float | int | str]:
    rows = pd.DataFrame([asdict(t) for t in trades])
    empty = {
        f"{label}_trades": 0,
        f"{label}_net_pct": 0.0,
        f"{label}_avg_bps": 0.0,
        f"{label}_win_rate": 0.0,
        f"{label}_pf": 0.0,
        f"{label}_max_dd_pct": 0.0,
        f"{label}_expect_r": 0.0,
    }
    if rows.empty:
        return empty

    if label == "train":
        rows = rows[rows["date"] <= train_end_date]
    elif label == "test":
        rows = rows[rows["date"] > train_end_date]

    if rows.empty:
        return empty

    ret = rows["net_return"].astype(float)
    gross_profit = ret[ret > 0].sum()
    gross_loss = -ret[ret < 0].sum()
    net, max_dd = equity_drawdown(ret)
    pf = gross_profit / gross_loss if gross_loss > 0 else math.inf
    return {
        f"{label}_trades": int(len(rows)),
        f"{label}_net_pct": round(net * 100, 2),
        f"{label}_avg_bps": round(ret.mean() * 10000, 2),
        f"{label}_win_rate": round((ret > 0).mean() * 100, 2),
        f"{label}_pf": round(pf, 3) if np.isfinite(pf) else 999.0,
        f"{label}_max_dd_pct": round(max_dd * 100, 2),
        f"{label}_expect_r": round(rows["r_multiple"].mean(), 3),
    }


def movement_study(df: pd.DataFrame) -> dict[str, object]:
    daily = (
        df.groupby("date")
        .agg(
            open=("Open", "first"),
            high=("High", "max"),
            low=("Low", "min"),
            close=("Close", "last"),
            volume=("Volume", "sum"),
            gap_pct=("gap_pct", "first"),
        )
        .reset_index()
    )
    daily["day_return_pct"] = daily["close"] / daily["open"] - 1
    daily["range_pct"] = (daily["high"] - daily["low"]) / daily["open"]
    daily["trend_efficiency"] = daily["day_return_pct"].abs() / daily["range_pct"]
    big = daily.nlargest(10, "range_pct")[
        ["date", "day_return_pct", "range_pct", "trend_efficiency", "gap_pct", "volume"]
    ].copy()
    trend_days = daily[daily["trend_efficiency"] >= 0.55]
    stats = {
        "days": int(len(daily)),
        "median_day_range_pct": round(daily["range_pct"].median() * 100, 2),
        "p75_day_range_pct": round(daily["range_pct"].quantile(0.75) * 100, 2),
        "p90_day_range_pct": round(daily["range_pct"].quantile(0.90) * 100, 2),
        "trend_day_share_pct": round(len(trend_days) / len(daily) * 100, 2),
        "median_abs_gap_pct": round(daily["gap_pct"].abs().median() * 100, 2),
        "top_range_days": big.round(4).to_dict(orient="records"),
    }

    # Opening range continuation: once the first 30m high/low breaks, how often
    # does the day close in the breakout direction?
    continuation: dict[str, dict[str, float | int]] = {}
    for bars in [3, 6, 9]:
        recs = []
        for _, day in df.groupby("date", sort=True):
            or_hi = day.iloc[:bars]["High"].max()
            or_lo = day.iloc[:bars]["Low"].min()
            after = day.iloc[bars:]
            long_break = after[after["Close"] > or_hi]
            short_break = after[after["Close"] < or_lo]
            if not long_break.empty:
                first = long_break.iloc[0]
                recs.append(
                    {
                        "dir": 1,
                        "from_break_to_close": day.iloc[-1]["Close"] / first["Close"] - 1,
                        "volume_ratio": first["vol_ratio20"],
                        "adx": first["ADX"],
                    }
                )
            if not short_break.empty:
                first = short_break.iloc[0]
                recs.append(
                    {
                        "dir": -1,
                        "from_break_to_close": first["Close"] / day.iloc[-1]["Close"] - 1,
                        "volume_ratio": first["vol_ratio20"],
                        "adx": first["ADX"],
                    }
                )
        r = pd.DataFrame(recs)
        if not r.empty:
            filt = r[(r["volume_ratio"] >= 1.2) & (r["adx"] >= 18)]
            continuation[f"or_{bars * 5}m_all"] = {
                "events": int(len(r)),
                "avg_bps_to_close": round(r["from_break_to_close"].mean() * 10000, 2),
                "positive_pct": round((r["from_break_to_close"] > 0).mean() * 100, 2),
            }
            continuation[f"or_{bars * 5}m_vol_adx"] = {
                "events": int(len(filt)),
                "avg_bps_to_close": round(filt["from_break_to_close"].mean() * 10000, 2),
                "positive_pct": round((filt["from_break_to_close"] > 0).mean() * 100, 2),
            }
    stats["opening_range_continuation"] = continuation
    return stats


def run_family_search(df: pd.DataFrame, train_end_date: str) -> tuple[pd.DataFrame, list[Trade]]:
    candidates: list[dict[str, object]] = []
    trade_bank: dict[str, list[Trade]] = {}
    day_frames = list(df.groupby("date", sort=True))

    def add_candidate(strategy: str, variant: str, trades: list[Trade]) -> None:
        if len(trades) == 0:
            return
        summary: dict[str, object] = {"strategy": strategy, "variant": variant}
        summary.update(summarize_trades(trades, train_end_date, "all"))
        summary.update(summarize_trades(trades, train_end_date, "train"))
        summary.update(summarize_trades(trades, train_end_date, "test"))
        candidates.append(summary)
        trade_bank[f"{strategy}|{variant}"] = trades

    # Opening range breakout.
    for params in itertools.product(
        [3, 6],
        ["long", "short"],
        [(9, 21), (13, 34)],
        [18, 22],
        [1.0, 1.3],
        [1.0, 1.3],
        [1.2, 1.6, 2.0],
        [44],
        [False, True],
    ):
        or_bars, side, ema_pair, adx_min, vol_min, stop_atr, target_r, latest_bar, daily = params
        fast, slow = ema_pair
        variant = (
            f"or={or_bars*5}m side={side} ema={fast}/{slow} adx>={adx_min} "
            f"vol>={vol_min} stop={stop_atr}ATR target={target_r}R "
            f"latest_bar={latest_bar} daily={daily}"
        )
        trades = backtest_daily_signals(
            day_frames,
            "opening_range_breakout",
            variant,
            opening_range_signal_fn(
                or_bars, side, fast, slow, adx_min, vol_min, stop_atr, latest_bar, daily
            ),
            target_r=target_r,
            trail_atr_mult=None,
            max_trades_per_day=1,
        )
        add_candidate("opening_range_breakout", variant, trades)

    # Donchian continuation breakout.
    for params in itertools.product(
        [15, 20, 30],
        ["long", "short"],
        [(8, 21), (13, 34)],
        [18, 22],
        [1.0, 1.3],
        [1.0, 1.3],
        [1.2, 1.6, 2.0],
        [9],
        [50],
        [False, True],
    ):
        lookback, side, ema_pair, adx_min, vol_min, stop_atr, target_r, earliest, latest, prev_filter = params
        fast, slow = ema_pair
        if earliest >= latest:
            continue
        variant = (
            f"n={lookback} side={side} ema={fast}/{slow} adx>={adx_min} "
            f"vol>={vol_min} stop={stop_atr}ATR target={target_r}R "
            f"bars={earliest}-{latest} prevday={prev_filter}"
        )
        trades = backtest_daily_signals(
            day_frames,
            "donchian_breakout",
            variant,
            donchian_signal_fn(
                lookback,
                side,
                fast,
                slow,
                adx_min,
                vol_min,
                stop_atr,
                earliest,
                latest,
                prev_filter,
            ),
            target_r=target_r,
            trail_atr_mult=None,
            max_trades_per_day=1,
        )
        add_candidate("donchian_breakout", variant, trades)

    # Trend pullback continuation.
    for params in itertools.product(
        ["long", "short"],
        [(9, 34), (13, 34), (21, 55)],
        [14, 18],
        [0.8, 1.0],
        [1.0, 1.3],
        [1.2, 1.6],
        [8],
        [50],
        [(45, 72), (50, 75)],
    ):
        side, ema_pair, adx_min, vol_min, stop_atr, target_r, earliest, latest, rsi_band = params
        fast, slow = ema_pair
        rsi_low, rsi_high = rsi_band
        if earliest >= latest:
            continue
        variant = (
            f"side={side} ema={fast}/{slow} adx>={adx_min} vol>={vol_min} "
            f"stop={stop_atr}ATR target={target_r}R bars={earliest}-{latest} "
            f"rsi={rsi_low}-{rsi_high}"
        )
        trades = backtest_daily_signals(
            day_frames,
            "vwap_ema_pullback",
            variant,
            pullback_signal_fn(
                side,
                fast,
                slow,
                adx_min,
                vol_min,
                stop_atr,
                earliest,
                latest,
                rsi_low,
                rsi_high,
            ),
            target_r=target_r,
            trail_atr_mult=None,
            max_trades_per_day=1,
        )
        add_candidate("vwap_ema_pullback", variant, trades)

    # VWAP mean reversion.
    for params in itertools.product(
        ["long", "short"],
        [1.0, 1.25, 1.5],
        [25, 30],
        [1.0, 1.3],
        [12],
        [50],
        [0.8, 1.0],
    ):
        side, band_atr, rsi_extreme, stop_atr, earliest, latest, target_r = params
        if earliest >= latest:
            continue
        variant = (
            f"side={side} band={band_atr}ATR rsi_extreme={rsi_extreme} "
            f"stop={stop_atr}ATR target={target_r}R bars={earliest}-{latest}"
        )
        trades = backtest_daily_signals(
            day_frames,
            "vwap_reversion",
            variant,
            vwap_reversion_signal_fn(side, band_atr, rsi_extreme, stop_atr, earliest, latest),
            target_r=target_r,
            trail_atr_mult=None,
            max_trades_per_day=1,
            max_hold_bars=18,
        )
        add_candidate("vwap_reversion", variant, trades)

    results = pd.DataFrame(candidates)
    if results.empty:
        return results, []

    # Penalize fragile train-only edge; select strategies that survive unseen data.
    results["selection_score"] = (
        results["train_net_pct"]
        + 4 * (results["train_pf"] - 1)
        + 0.04 * results["train_trades"]
        + results["train_avg_bps"] / 8
        + results["train_max_dd_pct"] / 2
    )
    results["validation_score"] = (
        results["test_net_pct"]
        + 4 * (results["test_pf"] - 1)
        + 0.03 * results["test_trades"]
        + results["test_avg_bps"] / 10
        + results["test_max_dd_pct"] / 2
    )
    all_results = results.copy()
    eligible = all_results[
        (results["train_trades"] >= 50)
        & (results["train_pf"] >= 1.15)
        & (results["train_avg_bps"] > 4)
        & (results["train_max_dd_pct"] > -15)
    ].copy()
    rank_source = eligible if not eligible.empty else all_results
    ranked = rank_source.sort_values(
        ["selection_score", "train_pf", "train_net_pct", "train_trades"],
        ascending=[False, False, False, False],
    )
    rest = all_results.drop(index=ranked.index).sort_values(
        ["selection_score", "train_pf", "train_net_pct", "train_trades"],
        ascending=[False, False, False, False],
    )
    results = pd.concat(
        [ranked, rest],
        axis=0,
    )
    results = results.reset_index(drop=True)
    best_key = f"{results.iloc[0]['strategy']}|{results.iloc[0]['variant']}"
    return results, trade_bank[best_key]


def first_signal_indices(mask: np.ndarray, bars_per_day: int = 75) -> np.ndarray:
    mask = np.asarray(mask, dtype=bool)
    usable = (len(mask) // bars_per_day) * bars_per_day
    shaped = mask[:usable].reshape(-1, bars_per_day)
    has_signal = shaped.any(axis=1)
    first_pos = shaped.argmax(axis=1)
    day_offsets = np.arange(shaped.shape[0]) * bars_per_day
    return day_offsets[has_signal] + first_pos[has_signal]


def simulate_index_trades(
    df: pd.DataFrame,
    signal_indices: np.ndarray,
    direction: int,
    strategy: str,
    variant: str,
    stop_distances: np.ndarray,
    target_r: float,
    max_hold_bars: int | None = None,
    cost_bps_per_side: float = COST_BPS_PER_SIDE,
) -> list[Trade]:
    open_ = df["Open"].to_numpy(float)
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    close = df["Close"].to_numpy(float)
    dt = df["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S").to_numpy()
    dates = df["date"].to_numpy()

    trades: list[Trade] = []
    for sig_idx in signal_indices:
        if sig_idx % 75 >= 73:
            continue
        entry_idx = int(sig_idx + 1)
        day_end = int((sig_idx // 75) * 75 + 74)
        final_idx = day_end if max_hold_bars is None else min(day_end, entry_idx + max_hold_bars)
        entry = float(open_[entry_idx])
        stop_distance = float(stop_distances[sig_idx])
        if not np.isfinite(stop_distance) or stop_distance <= 0:
            continue

        stop = entry - direction * stop_distance
        target = entry + direction * target_r * stop_distance
        exit_price = float(close[final_idx])
        exit_idx = final_idx
        exit_reason = "eod" if final_idx == day_end else "timeout"

        for pos in range(entry_idx, final_idx + 1):
            if direction == 1:
                stop_hit = low[pos] <= stop
                target_hit = high[pos] >= target
            else:
                stop_hit = high[pos] >= stop
                target_hit = low[pos] <= target

            if stop_hit and target_hit:
                exit_price = stop
                exit_idx = pos
                exit_reason = "stop_same_bar"
                break
            if stop_hit:
                exit_price = stop
                exit_idx = pos
                exit_reason = "stop"
                break
            if target_hit:
                exit_price = target
                exit_idx = pos
                exit_reason = "target"
                break

        gross = direction * (exit_price / entry - 1)
        net = gross - (2 * cost_bps_per_side / 10000)
        trades.append(
            Trade(
                strategy=strategy,
                variant=variant,
                direction=direction,
                entry_time=str(dt[entry_idx]),
                exit_time=str(dt[exit_idx]),
                entry=entry,
                exit=float(exit_price),
                gross_return=float(gross),
                net_return=float(net),
                r_multiple=float(direction * (exit_price - entry) / stop_distance),
                exit_reason=exit_reason,
                date=str(dates[entry_idx]),
            )
        )
    return trades


def run_family_search_fast(df: pd.DataFrame, train_end_date: str) -> tuple[pd.DataFrame, list[Trade]]:
    candidates: list[dict[str, object]] = []
    trade_bank: dict[str, list[Trade]] = {}

    close = df["Close"].to_numpy(float)
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    vwap = df["vwap"].to_numpy(float)
    adx = df["ADX"].to_numpy(float)
    atr = df["atr14_calc"].to_numpy(float)
    vol_ratio = df["vol_ratio20"].to_numpy(float)
    bar = df["bar_no"].to_numpy(int)
    rsi14 = df["rsi14"].to_numpy(float)
    prev_close_arr = np.r_[np.nan, close[:-1]]
    valid_base = np.isfinite(atr) & np.isfinite(vol_ratio)
    daily_up = df["daily_trend_up"].fillna(False).to_numpy(bool)
    daily_down = df["daily_trend_down"].fillna(False).to_numpy(bool)
    prev_high = df["prev_high"].to_numpy(float)
    prev_low = df["prev_low"].to_numpy(float)

    def add_candidate(
        strategy: str,
        variant: str,
        mask: np.ndarray,
        direction: int,
        stop_atr: float,
        target_r: float,
        max_hold_bars: int | None = None,
    ) -> None:
        stop_distances = stop_atr * atr
        idx = first_signal_indices(mask & valid_base & np.isfinite(stop_distances))
        if len(idx) == 0:
            return
        trades = simulate_index_trades(
            df,
            idx,
            direction,
            strategy,
            variant,
            stop_distances,
            target_r,
            max_hold_bars=max_hold_bars,
        )
        if not trades:
            return
        summary: dict[str, object] = {"strategy": strategy, "variant": variant}
        summary.update(summarize_trades(trades, train_end_date, "all"))
        summary.update(summarize_trades(trades, train_end_date, "train"))
        summary.update(summarize_trades(trades, train_end_date, "test"))
        candidates.append(summary)
        trade_bank[f"{strategy}|{variant}"] = trades

    for or_bars, side, ema_pair, adx_min, vol_min, stop_atr, target_r, latest_bar, daily in itertools.product(
        [3, 6, 9],
        ["long", "short"],
        [(9, 21), (13, 34), (21, 55)],
        [18, 22],
        [1.0, 1.3],
        [1.0, 1.3, 1.6],
        [1.2, 1.6, 2.0],
        [44, 56],
        [False, True],
    ):
        fast, slow = ema_pair
        ema_fast = df[f"ema{fast}"].to_numpy(float)
        ema_slow = df[f"ema{slow}"].to_numpy(float)
        if side == "long":
            mask = (
                (bar >= or_bars)
                & (bar < latest_bar)
                & (close > df[f"or_hi_{or_bars}"].to_numpy(float))
                & (close > vwap)
                & (ema_fast > ema_slow)
                & (adx >= adx_min)
                & (vol_ratio >= vol_min)
                & ((daily_up) if daily else True)
            )
            direction = 1
        else:
            mask = (
                (bar >= or_bars)
                & (bar < latest_bar)
                & (close < df[f"or_lo_{or_bars}"].to_numpy(float))
                & (close < vwap)
                & (ema_fast < ema_slow)
                & (adx >= adx_min)
                & (vol_ratio >= vol_min)
                & ((daily_down) if daily else True)
            )
            direction = -1
        variant = (
            f"or={or_bars*5}m side={side} ema={fast}/{slow} adx>={adx_min} "
            f"vol>={vol_min} stop={stop_atr}ATR target={target_r}R "
            f"latest_bar={latest_bar} daily={daily}"
        )
        add_candidate("opening_range_breakout", variant, mask, direction, stop_atr, target_r)

    for lookback, side, ema_pair, adx_min, vol_min, stop_atr, target_r, earliest, latest, prev_filter in itertools.product(
        [15, 20, 30, 40],
        ["long", "short"],
        [(8, 21), (13, 34), (21, 55)],
        [18, 22],
        [1.0, 1.3],
        [1.0, 1.3, 1.6],
        [1.2, 1.6, 2.0],
        [9, 12],
        [50, 56],
        [False, True],
    ):
        fast, slow = ema_pair
        ema_fast = df[f"ema{fast}"].to_numpy(float)
        ema_slow = df[f"ema{slow}"].to_numpy(float)
        if side == "long":
            mask = (
                (bar >= earliest)
                & (bar < latest)
                & (close > df[f"donch_hi_{lookback}"].to_numpy(float))
                & (close > vwap)
                & (ema_fast > ema_slow)
                & (adx >= adx_min)
                & (vol_ratio >= vol_min)
                & ((close > prev_high) if prev_filter else True)
            )
            direction = 1
        else:
            mask = (
                (bar >= earliest)
                & (bar < latest)
                & (close < df[f"donch_lo_{lookback}"].to_numpy(float))
                & (close < vwap)
                & (ema_fast < ema_slow)
                & (adx >= adx_min)
                & (vol_ratio >= vol_min)
                & ((close < prev_low) if prev_filter else True)
            )
            direction = -1
        variant = (
            f"n={lookback} side={side} ema={fast}/{slow} adx>={adx_min} "
            f"vol>={vol_min} stop={stop_atr}ATR target={target_r}R "
            f"bars={earliest}-{latest} prevday={prev_filter}"
        )
        add_candidate("donchian_breakout", variant, mask, direction, stop_atr, target_r)

    for side, ema_pair, adx_min, vol_min, stop_atr, target_r, earliest, latest, rsi_band in itertools.product(
        ["long", "short"],
        [(9, 34), (13, 34), (21, 55)],
        [14, 18, 22],
        [0.8, 1.0],
        [1.0, 1.3],
        [1.2, 1.6, 2.0],
        [8, 12],
        [50, 60],
        [(45, 72), (50, 75), (40, 68)],
    ):
        fast, slow = ema_pair
        rsi_low, rsi_high = rsi_band
        ema_fast = df[f"ema{fast}"].to_numpy(float)
        ema_slow = df[f"ema{slow}"].to_numpy(float)
        if side == "long":
            touched = (low <= ema_fast) | (low <= vwap)
            recovered = (close > ema_fast) & (close > prev_close_arr)
            mask = (
                (bar >= earliest)
                & (bar < latest)
                & (close > vwap)
                & (ema_fast > ema_slow)
                & (adx >= adx_min)
                & (vol_ratio >= vol_min)
                & (rsi14 >= rsi_low)
                & (rsi14 <= rsi_high)
                & touched
                & recovered
            )
            direction = 1
        else:
            touched = (high >= ema_fast) | (high >= vwap)
            recovered = (close < ema_fast) & (close < prev_close_arr)
            mask = (
                (bar >= earliest)
                & (bar < latest)
                & (close < vwap)
                & (ema_fast < ema_slow)
                & (adx >= adx_min)
                & (vol_ratio >= vol_min)
                & (rsi14 >= 100 - rsi_high)
                & (rsi14 <= 100 - rsi_low)
                & touched
                & recovered
            )
            direction = -1
        variant = (
            f"side={side} ema={fast}/{slow} adx>={adx_min} vol>={vol_min} "
            f"stop={stop_atr}ATR target={target_r}R bars={earliest}-{latest} "
            f"rsi={rsi_low}-{rsi_high}"
        )
        add_candidate("vwap_ema_pullback", variant, mask, direction, stop_atr, target_r)

    for side, band_atr, rsi_extreme, stop_atr, earliest, latest, target_r in itertools.product(
        ["long", "short"],
        [1.0, 1.25, 1.5],
        [25, 30, 35],
        [1.0, 1.3, 1.6],
        [12],
        [50, 56],
        [0.8, 1.0, 1.2],
    ):
        if side == "long":
            mask = (
                (bar >= earliest)
                & (bar < latest)
                & (close < vwap - band_atr * atr)
                & (rsi14 <= rsi_extreme)
            )
            direction = 1
        else:
            mask = (
                (bar >= earliest)
                & (bar < latest)
                & (close > vwap + band_atr * atr)
                & (rsi14 >= 100 - rsi_extreme)
            )
            direction = -1
        variant = (
            f"side={side} band={band_atr}ATR rsi_extreme={rsi_extreme} "
            f"stop={stop_atr}ATR target={target_r}R bars={earliest}-{latest}"
        )
        add_candidate("vwap_reversion", variant, mask, direction, stop_atr, target_r, max_hold_bars=18)

    results = pd.DataFrame(candidates)
    if results.empty:
        return results, []

    results["selection_score"] = (
        results["train_net_pct"]
        + 4 * (results["train_pf"] - 1)
        + 0.04 * results["train_trades"]
        + results["train_avg_bps"] / 8
        + results["train_max_dd_pct"] / 2
    )
    results["validation_score"] = (
        results["test_net_pct"]
        + 4 * (results["test_pf"] - 1)
        + 0.03 * results["test_trades"]
        + results["test_avg_bps"] / 10
        + results["test_max_dd_pct"] / 2
    )
    all_results = results.copy()
    eligible = all_results[
        (results["train_trades"] >= 50)
        & (results["train_pf"] >= 1.15)
        & (results["train_avg_bps"] > 4)
        & (results["train_max_dd_pct"] > -15)
    ].copy()
    rank_source = eligible if not eligible.empty else all_results
    ranked = rank_source.sort_values(
        ["selection_score", "train_pf", "train_net_pct", "train_trades"],
        ascending=[False, False, False, False],
    )
    rest = all_results.drop(index=ranked.index).sort_values(
        ["selection_score", "train_pf", "train_net_pct", "train_trades"],
        ascending=[False, False, False, False],
    )
    results = pd.concat([ranked, rest], axis=0).reset_index(drop=True)
    best_key = f"{results.iloc[0]['strategy']}|{results.iloc[0]['variant']}"
    return results, trade_bank[best_key]


def stress_costs(trades: list[Trade], costs_bps: list[float]) -> list[dict[str, object]]:
    rows = pd.DataFrame([asdict(t) for t in trades])
    if rows.empty:
        return []
    out = []
    gross = rows["gross_return"].astype(float)
    for cost in costs_bps:
        net = gross - 2 * cost / 10000
        total, dd = equity_drawdown(net)
        gp = net[net > 0].sum()
        gl = -net[net < 0].sum()
        out.append(
            {
                "cost_bps_per_side": cost,
                "trades": int(len(net)),
                "net_pct": round(total * 100, 2),
                "avg_bps": round(net.mean() * 10000, 2),
                "win_rate_pct": round((net > 0).mean() * 100, 2),
                "profit_factor": round(float(gp / gl), 3) if gl > 0 else 999.0,
                "max_dd_pct": round(dd * 100, 2),
            }
        )
    return out


def monthly_table(trades: list[Trade]) -> pd.DataFrame:
    rows = pd.DataFrame([asdict(t) for t in trades])
    if rows.empty:
        return pd.DataFrame()
    rows["entry_time"] = pd.to_datetime(rows["entry_time"])
    rows["month"] = rows["entry_time"].dt.to_period("M").astype(str)
    rows["net_return"] = rows["net_return"].astype(float)
    return (
        rows.groupby("month")
        .agg(
            trades=("net_return", "size"),
            net_pct=("net_return", lambda s: round(((1 + s).prod() - 1) * 100, 2)),
            avg_bps=("net_return", lambda s: round(s.mean() * 10000, 2)),
            win_rate=("net_return", lambda s: round((s > 0).mean() * 100, 2)),
        )
        .reset_index()
    )


def main() -> None:
    df = load_data()
    dates = sorted(df["date"].unique())
    train_end_date = dates[int(len(dates) * 0.65) - 1]
    movement = movement_study(df)
    results, best_trades = run_family_search_fast(df, train_end_date)

    top = results.head(25).copy()
    trades_df = pd.DataFrame([asdict(t) for t in best_trades])
    month = monthly_table(best_trades)
    stress = stress_costs(best_trades, [0, 3, 5, 8, 10, 15])

    all_path = OUTPUT_DIR / "cgpower_strategy_all_results.csv"
    top_path = OUTPUT_DIR / "cgpower_strategy_top_results.csv"
    trades_path = OUTPUT_DIR / "cgpower_strategy_best_trades.csv"
    month_path = OUTPUT_DIR / "cgpower_strategy_best_monthly.csv"
    json_path = OUTPUT_DIR / "cgpower_strategy_research_summary.json"
    results.to_csv(all_path, index=False)
    top.to_csv(top_path, index=False)
    trades_df.to_csv(trades_path, index=False)
    month.to_csv(month_path, index=False)
    json_path.write_text(
        json.dumps(
            {
                "data_path": str(DATA_PATH),
                "rows_used": int(len(df)),
                "date_range": [str(df["Datetime"].min()), str(df["Datetime"].max())],
                "trading_days_used": int(df["date"].nunique()),
                "train_end_date": train_end_date,
                "cost_bps_per_side": COST_BPS_PER_SIDE,
                "movement_study": movement,
                "best_strategy": top.head(1).to_dict(orient="records")[0],
                "stress_costs": stress,
                "output_files": {
                    "all_results": str(all_path),
                    "top_results": str(top_path),
                    "best_trades": str(trades_path),
                    "best_monthly": str(month_path),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("ROWS_USED", len(df))
    print("DAYS_USED", df["date"].nunique())
    print("TRAIN_END_DATE", train_end_date)
    print("MOVEMENT_STUDY")
    print(json.dumps(movement, indent=2)[:4000])
    print("TOP_RESULTS")
    cols = [
        "strategy",
        "variant",
        "all_trades",
        "all_net_pct",
        "all_avg_bps",
        "all_win_rate",
        "all_pf",
        "all_max_dd_pct",
        "train_trades",
        "train_net_pct",
        "train_avg_bps",
        "train_pf",
        "test_trades",
        "test_net_pct",
        "test_avg_bps",
        "test_pf",
        "test_max_dd_pct",
        "selection_score",
        "validation_score",
    ]
    print(top[cols].to_string(index=False, max_colwidth=120))
    print("STRESS_COSTS")
    print(pd.DataFrame(stress).to_string(index=False))
    print("MONTHLY")
    print(month.to_string(index=False))
    print("OUTPUTS")
    print(all_path)
    print(top_path)
    print(trades_path)
    print(month_path)
    print(json_path)


if __name__ == "__main__":
    main()
