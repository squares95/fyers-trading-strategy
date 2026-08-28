"""Run the same session and pre-market research framework on HDFCBANK."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from Research.CGPOWER import cgpower_session_microstructure as sm, premarket_context_analysis as pm

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CHARTS = OUT / "session_charts"
HDFC_PATH = ROOT / "Data" / "HDFCBANK" / "HDFCBANK_1MIN.csv"
NIFTY_PATH = ROOT / "Data" / "NIFTY" / "NIFTY_1MIN.csv"
DISCOVERY_END = pd.Timestamp("2025-06-30")
HOLDOUT_START = pd.Timestamp("2025-07-01")


def prepare_context(
    daily: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    source = ROOT / "Research" / "CGPOWER"
    external = {
        "nasdaq": pd.read_csv(source / "external_nasdaq_daily.csv", parse_dates=["Date"]),
        "dow": pd.read_csv(source / "external_dow_daily.csv", parse_dates=["Date"]),
        "vix": pd.read_csv(source / "external_india_vix_daily.csv", parse_dates=["Date"]),
    }
    context = daily.reset_index().sort_values("Date")
    context["day_range"] = context["High"] / context["Low"] - 1
    for prefix, data in external.items():
        context = pd.merge_asof(
            context.sort_values("Date"),
            pm.make_available_next_day(data, prefix),
            left_on="Date",
            right_on="AvailableDate",
            direction="backward",
            tolerance=pd.Timedelta(days=4),
        ).drop(columns=["AvailableDate"])
    context["us_context"] = np.select(
        [
            (context["nasdaq_return"] > 0) & (context["dow_return"] > 0),
            (context["nasdaq_return"] < 0) & (context["dow_return"] < 0),
        ],
        ["both_green", "both_red"],
        default="mixed",
    )
    context["vix_regime"] = np.where(context["vix_close"] > 15, "above_15", "at_or_below_15")
    context["nifty_gap_proxy"] = pd.cut(
        context["nifty_gap"],
        [-np.inf, -0.002, 0.002, np.inf],
        labels=["red_below_-0.2%", "flat_+-0.2%", "green_above_+0.2%"],
    )
    context["combined_proxy"] = np.select(
        [
            (context["us_context"] == "both_green") & (context["nifty_gap"] > 0.002),
            (context["us_context"] == "both_red") & (context["nifty_gap"] < -0.002),
        ],
        ["bullish_agreement", "bearish_agreement"],
        default="mixed_or_conflict",
    )
    results = pd.concat(
        [
            pm.summarize(context.groupby("us_context"), "Previous US close"),
            pm.summarize(context.groupby("vix_regime"), "Previous India VIX close"),
            pm.summarize(
                context.groupby("nifty_gap_proxy", observed=True), "NIFTY opening-gap proxy"
            ),
            pm.summarize(context.groupby("combined_proxy"), "US + NIFTY-gap agreement"),
        ],
        ignore_index=True,
    )
    trade_results, replay = pm.context_trade_tests(context)
    return context, results, trade_results, replay


def relationship_metrics(daily: pd.DataFrame, symbol: str) -> dict[str, float | str]:
    matched = daily.dropna(subset=["nifty_gap", "nifty_r15", "nifty_daily_return"])
    return {
        "Symbol": symbol,
        "Sessions": len(daily),
        "GapCorrelation": matched["gap"].corr(matched["nifty_gap"]),
        "First15Correlation": matched["r15"].corr(matched["nifty_r15"]),
        "DailyCorrelation": matched["daily_return"].corr(matched["nifty_daily_return"]),
        "GapDirectionMatch": (np.sign(matched["gap"]) == np.sign(matched["nifty_gap"])).mean(),
        "First15DirectionMatch": (np.sign(matched["r15"]) == np.sign(matched["nifty_r15"])).mean(),
        "DailyDirectionMatch": (
            np.sign(matched["daily_return"]) == np.sign(matched["nifty_daily_return"])
        ).mean(),
        "MedianAbsFirst30": daily["r30"].abs().median(),
        "MedianOpening30VolumeShare": daily["opening30_volume_share"].median(),
        "MedianAbsClosing30": daily["r_close30"].abs().median(),
        "BothOpeningSidesBroken": daily["break_type"]
        .isin(["low_then_high", "high_then_low"])
        .mean(),
    }


def chart_context(results: pd.DataFrame) -> None:
    display = results[
        results["Test"].isin(["Previous US close", "US + NIFTY-gap agreement"])
    ].copy()
    display["Category"] = display["us_context"].fillna(display["combined_proxy"])
    x = np.arange(len(display))
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x - 0.2, display["CGGapUpRate"] * 100, 0.2, label="HDFC gap up")
    ax.bar(x, display["CGFirst15UpRate"] * 100, 0.2, label="HDFC first 15m up")
    ax.bar(x + 0.2, display["CGDayUpRate"] * 100, 0.2, label="HDFC day up")
    ax.axhline(50, color="#6B7280", linewidth=0.8)
    ax.set_xticks(x, display["Category"], rotation=20, ha="right")
    ax.set_ylabel("Up frequency (%)")
    ax.set_title("HDFCBANK: premarket context versus actual path", loc="left", weight="bold")
    ax.legend(frameon=False, ncol=3)
    ax.grid(axis="y", alpha=0.18)
    fig.tight_layout()
    fig.savefig(CHARTS / "04_premarket_context.png", dpi=180)
    plt.close(fig)


def chart_replays(replay: pd.DataFrame, minutes: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 2, figsize=(13, 11), sharex=True)
    for ax, (_, row) in zip(axes.flat, replay.iterrows()):
        day = minutes[minutes["Date"] == row["Date"]].sort_values("Datetime")
        path = (day["Close"] / day.iloc[0]["Open"] - 1) * 100
        ax.plot(
            np.arange(len(day)),
            path,
            color="#195B8A" if row["Direction"] > 0 else "#F28E2B",
            linewidth=1.4,
        )
        ax.axvline(14, color="#6B7280", linestyle="--", linewidth=0.8)
        ax.axhline(0, color="#6B7280", linewidth=0.7)
        ax.set_title(
            f"{row['Date'].date()} | {row['combined_proxy']} | net {row['NetReturn']:.2%}",
            loc="left",
            fontsize=10,
            weight="bold",
        )
        ax.set_ylabel("From open (%)")
        ax.grid(alpha=0.15)
    for ax in axes[-1]:
        ax.set_xlabel("Minutes after 09:15")
    fig.suptitle(
        "HDFCBANK mental paper trades: best and worst identical-context outcomes",
        x=0.06,
        ha="left",
        weight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(CHARTS / "05_mental_replays.png", dpi=180)
    plt.close(fig)


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    sm.TRAIN_END = DISCOVERY_END
    sm.HOLDOUT_START = HOLDOUT_START
    sm.CHARTS = CHARTS

    minutes = sm.valid_sessions(sm.load_minutes(HDFC_PATH))
    nifty_minutes = sm.load_minutes(NIFTY_PATH)
    daily = sm.add_nifty_features(sm.build_daily_features(minutes), nifty_minutes)
    profile = sm.minute_profile(minutes)
    opening, breakouts, closing = sm.conditional_tables(daily)

    grid, rule, cutoff = sm.discover_opening_rule(daily, minutes)
    opening_results = sm.strategy_summary(rule, cutoff, daily, minutes)
    sweep_grid, sweep_best = sm.discover_sweep_rule(daily, minutes)
    sweep_results, sweep_replay = sm.sweep_summary(sweep_best, daily, minutes)
    orb_grid, orb_best = sm.discover_orb_rule(daily, minutes)
    orb_results, orb_replay = sm.orb_summary(orb_best, daily, minutes)

    cg_open_rule = sm.Rule("cg_frozen_opening_drive", 0.15, 0.70, 0.50, 2.0)
    transferred = []
    for name, trades_train, trades_test in (
        (
            "CG_frozen_opening_drive",
            sm.evaluate_rule(cg_open_rule, daily, minutes, 0.9865, end=DISCOVERY_END),
            sm.evaluate_rule(cg_open_rule, daily, minutes, 0.9865, start=HOLDOUT_START),
        ),
        (
            "CG_frozen_liquidity_sweep",
            sm.evaluate_sweep_rule(
                daily, minutes, "14:30", "midpoint", 1.0, 0.0, end=DISCOVERY_END
            ),
            sm.evaluate_sweep_rule(
                daily, minutes, "14:30", "midpoint", 1.0, 0.0, start=HOLDOUT_START
            ),
        ),
        (
            "CG_frozen_ORB",
            sm.evaluate_orb_rule(
                daily,
                minutes,
                "11:30",
                "opposite_boundary",
                1.5,
                0.0,
                0.70,
                False,
                end=DISCOVERY_END,
            ),
            sm.evaluate_orb_rule(
                daily,
                minutes,
                "11:30",
                "opposite_boundary",
                1.5,
                0.0,
                0.70,
                False,
                start=HOLDOUT_START,
            ),
        ),
    ):
        transferred.extend(
            [
                {"Rule": name, "Sample": "Discovery", **sm.metrics(trades_train)},
                {"Rule": name, "Sample": "Holdout", **sm.metrics(trades_test)},
            ]
        )
    transferred = pd.DataFrame(transferred)

    context, context_results, context_trades, context_replay = prepare_context(daily)
    hdfc_relationship = relationship_metrics(daily, "HDFCBANK")
    cg_daily = pd.read_csv(
        ROOT / "Research" / "CGPOWER" / "session_daily_features.csv", parse_dates=["Date"]
    ).set_index("Date")
    comparison = pd.DataFrame([hdfc_relationship, relationship_metrics(cg_daily, "CGPOWER")])

    daily.to_csv(OUT / "session_daily_features.csv")
    profile.to_csv(OUT / "minute_of_day_profile.csv")
    opening.to_csv(OUT / "opening_strength_outcomes.csv")
    breakouts.to_csv(OUT / "opening_range_outcomes.csv")
    closing.to_csv(OUT / "closing_strength_outcomes.csv")
    grid.to_csv(OUT / "opening_rule_grid_train.csv", index=False)
    opening_results.to_csv(OUT / "opening_rule_train_holdout.csv", index=False)
    sweep_grid.to_csv(OUT / "liquidity_sweep_grid_train.csv", index=False)
    sweep_results.to_csv(OUT / "liquidity_sweep_train_holdout.csv", index=False)
    orb_grid.to_csv(OUT / "opening_range_breakout_grid_train.csv", index=False)
    orb_results.to_csv(OUT / "opening_range_breakout_train_holdout.csv", index=False)
    transferred.to_csv(OUT / "cg_rules_transferred_to_hdfcbank.csv", index=False)
    context.to_csv(OUT / "premarket_context_daily.csv", index=False)
    context_results.to_csv(OUT / "premarket_context_results.csv", index=False)
    context_trades.to_csv(OUT / "premarket_trade_filter_results.csv", index=False)
    context_replay.to_csv(OUT / "premarket_mental_replays.csv", index=False)
    comparison.to_csv(OUT / "hdfcbank_vs_cgpower.csv", index=False)

    sm.chart_activity(profile, "HDFCBANK")
    sm.chart_conditionals(opening, closing)
    sm.chart_breakouts(breakouts)
    chart_context(context_results)
    chart_replays(context_replay, minutes)

    report = f"""# HDFCBANK session research

Coverage: {daily.index.min().date()} to {daily.index.max().date()}, {len(daily)} complete sessions. Discovery ends {DISCOVERY_END.date()}; holdout begins {HOLDOUT_START.date()}.

## Cross-asset rule transfer

{transferred.to_string(index=False, formatters={'WinRate': lambda x: f'{x:.1%}', 'ProfitFactor': lambda x: f'{x:.2f}', 'Expectancy': lambda x: f'{x:.3%}', 'MaxDrawdown': lambda x: f'{x:.2%}'})}

## HDFCBANK-specific discovery and holdout

Opening drive:\n{opening_results.to_string(index=False)}

Liquidity sweep:\n{sweep_results.to_string(index=False)}

Opening-range breakout:\n{orb_results.to_string(index=False)}

## NIFTY relationship comparison

{comparison.to_string(index=False)}

## Premarket permission filters

{context_trades.to_string(index=False)}

No result should be promoted unless the holdout remains profitable after costs and the mental losing replays remain tolerable.
"""
    (OUT / "hdfcbank_findings.md").write_text(report, encoding="utf-8")

    print(
        f"HDFCBANK sessions: {len(daily)} ({daily.index.min().date()}..{daily.index.max().date()})"
    )
    print("\nTRANSFERRED RULES\n", transferred.to_string(index=False))
    print("\nHDFC-SPECIFIC ORB\n", orb_results.to_string(index=False))
    print("\nCOMPARISON\n", comparison.to_string(index=False))
    print("\nPREMARKET\n", context_trades.to_string(index=False))


if __name__ == "__main__":
    main()
