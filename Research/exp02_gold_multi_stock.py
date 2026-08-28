"""
Experiment 2: Multi-Stock Gold Strategy Screen
Finds which stocks become PROFITABLE with SUPER GOLD (regime + strength filters).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_config() -> dict:
    config_path = Path("Config/groq_config.json")
    if not config_path.exists():
        return {}
    try:
        with open(config_path) as f:
            return json.load(f)
    except:
        return {}


CONFIG = load_config()
GROQ_API_KEY = CONFIG.get("groq_api_key", "")


def run_gold_v2(symbol: str) -> dict:
    """Run Gold strategy using the working approach."""
    try:
        # Imports
        from Strategies.G01.backtest import backtest
        from Strategies.G01.features import prepare_features
        from Strategies.G01.Gold import get_super_gold_config
        from Strategies.G01.regime_filter import daily_regime_table
        from Strategies.G01.signals import generate_signals
        from Strategies.G01.stats import summarize_trades
        from Strategies.G01.strength_scorer import signal_strength_table

        data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
        if not data_path.exists():
            return {"symbol": symbol, "error": "No data"}

        config = get_super_gold_config()

        # Load and prepare data
        df = prepare_features(data_path)

        # Generate signals
        signals = generate_signals(df, config)

        if len(signals) == 0:
            return {"symbol": symbol, "trades": 0, "note": "No signals generated"}

        # Apply regime filter
        regime = daily_regime_table(df)
        tradeable_dates = set(regime.loc[regime["regime_tradeable"], "date"])
        signals = signals[signals["date"].isin(tradeable_dates)].copy()

        if len(signals) == 0:
            return {"symbol": symbol, "trades": 0, "note": "No signals after regime filter"}

        # Calculate strength scores
        strength = signal_strength_table(df, signals, config)

        # Merge strength into signals
        signals = signals.merge(
            strength[["date", "direction", "signal_strength", "strength_trigger_component"]],
            on=["date", "direction"],
            how="left",
        )

        # Apply strength filter
        min_strength = 45
        min_trigger = 0.15
        signals = signals[
            (signals["signal_strength"] >= min_strength)
            & (signals["strength_trigger_component"] >= min_trigger)
        ].copy()

        if len(signals) == 0:
            return {"symbol": symbol, "trades": 0, "note": "No signals after strength filter"}

        # Backtest
        trades = backtest(df, signals, config)
        stats = summarize_trades(trades)

        return {
            "symbol": symbol,
            "net_pct": round(stats.get("net_pct", 0), 2),
            "profit_factor": round(stats.get("profit_factor", 0), 3),
            "win_rate_pct": round(stats.get("win_rate_pct", 0), 1),
            "max_dd_pct": round(stats.get("max_dd_pct", 0), 2),
            "trades": len(trades),
            "avg_bps": round(stats.get("avg_bps", 0), 2),
            "regime_days": len(tradeable_dates),
            "signals_after_regime": len(signals[signals["date"].isin(tradeable_dates)]),
        }

    except Exception as e:
        return {"symbol": symbol, "error": str(e)[:80]}


def get_all_symbols() -> list:
    """Get all symbols with 5MIN data."""
    data_dir = Path("Data")
    if not data_dir.exists():
        return []

    symbols = []
    for symbol_dir in data_dir.iterdir():
        if symbol_dir.is_dir():
            csv_path = symbol_dir / f"{symbol_dir.name}_5MIN.csv"
            if csv_path.exists():
                symbols.append(symbol_dir.name)
    return sorted(symbols)


def ask_groq(results: list) -> str:
    """Ask Groq to rank stocks."""
    if not GROQ_API_KEY:
        return "ERROR: No API key"

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=CONFIG.get("groq_base_url", "https://api.groq.com/openai/v1"),
            api_key=GROQ_API_KEY,
        )

        # Sort by profit factor
        valid = [r for r in results if "net_pct" in r and "error" not in r]
        valid.sort(key=lambda x: (x.get("net_pct", 0), x.get("profit_factor", 0)), reverse=True)

        result_text = "\n".join(
            [
                f"- {r['symbol']}: Net={r['net_pct']:+.1f}%, PF={r['profit_factor']:.2f}, "
                f"WR={r['win_rate_pct']:.0f}%, DD={r['max_dd_pct']:.1f}%, Trades={r['trades']}"
                for r in valid
            ]
        )

        prompt = f"""You are a quantitative researcher. Rank these stocks.

## SUPER GOLD Strategy Results
{result_text}

## Strategy
- VWAP-EMA Pullback with regime filter (turnover > 1B, range > 2%)
- Strength filter (score >= 45, trigger >= 0.15)
- Stop: 1.3x ATR, Target: 3.9R

## Task
1. TOP 3 stocks to trade (highest net return + good PF + acceptable DD)
2. Stocks to AVOID
3. 5 new stocks to test (based on patterns)

Format JSON:
{{
    "top_picks": [{{"symbol": "X", "net": N, "pf": N, "why": "reason"}}],
    "avoid": [{{"symbol": "X", "why": "reason"}}],
    "new_candidates": [{{"symbol": "X", "reason": "why"}}]
}}
"""

        response = client.chat.completions.create(
            model=CONFIG.get("default_model", "openai/gpt-oss-120b"),
            messages=[
                {"role": "system", "content": "You are a quantitative researcher. JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.3,
        )
        return response.choices[0].message.content

    except Exception as e:
        return f"ERROR: {e!s}"


def main():
    print("=" * 60)
    print("EXPERIMENT 2: Multi-Stock Gold Screen")
    print("=" * 60)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n")

    if not GROQ_API_KEY:
        print("[!] GROQ_API_KEY not set in Config/groq_config.json")
        return

    symbols = get_all_symbols()
    print(f"Found {len(symbols)} symbols: {symbols}\n")

    print("Running SUPER GOLD on all stocks...")
    results = []
    for sym in symbols:
        print(f"  {sym}...", end=" ", flush=True)
        r = run_gold_v2(sym)
        results.append(r)
        if "error" in r:
            print(f"[X] {r['error']}")
        elif "note" in r:
            print(f"[-] {r['note']}")
        else:
            print(
                f"[OK] Net: {r['net_pct']:+.1f}%, PF: {r['profit_factor']:.2f}, Trades: {r['trades']}"
            )

    # Sort by net return
    valid = [r for r in results if "net_pct" in r and "error" not in r]
    valid.sort(key=lambda x: x["net_pct"], reverse=True)

    print("\n" + "=" * 60)
    print("RANKED RESULTS (by Net Return)")
    print("=" * 60)
    print(f"{'Symbol':<15} {'Net%':>8} {'PF':>6} {'WR%':>6} {'DD%':>8} {'Trades':>7}")
    print("-" * 60)
    for r in valid:
        print(
            f"{r['symbol']:<15} {r['net_pct']:>+8.1f} {r['profit_factor']:>6.2f} "
            f"{r['win_rate_pct']:>6.1f} {r['max_dd_pct']:>8.1f} {r['trades']:>7}"
        )
    print("-" * 60)
    print(f"Winners: {len([r for r in valid if r['net_pct'] > 0])} / {len(valid)}")

    # Ask Groq
    print("\n" + "=" * 60)
    print("GROQ ANALYSIS")
    print("=" * 60)
    analysis = ask_groq(results)
    print(analysis.encode("ascii", "replace").decode())

    # Save
    output_dir = Path("Research/GroqAnalysis")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(output_dir / f"exp02_{ts}.json", "w") as f:
        json.dump(
            {
                "experiment": "exp02_gold_multi_stock",
                "timestamp": ts,
                "results": results,
                "analysis": analysis,
            },
            f,
            indent=2,
        )

    print(f"\n[Saved] Research/GroqAnalysis/exp02_{ts}.json")


if __name__ == "__main__":
    main()
