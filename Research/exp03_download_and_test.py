"""
Experiment 3: Download New Candidates + Test
Download data for Groq's suggested stocks and test SUPER GOLD on them.
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


# New candidates from Groq
NEW_CANDIDATES = [
    "INDUSINDBK",
    "HINDUNILVR",
    "ASIANPAINT",
    "DRREDDY",
    "HDFCBANK",
    "RELIANCE",
    "SBIN",
    "ICICIBANK",
]


def download_data(symbol: str, days: int = 500) -> bool:
    """Download data for a symbol using Main.py."""
    try:
        from Main import RunExample

        print(f"    Downloading {symbol} ({days} days)...", end=" ")
        RunExample("download", [symbol], downloadTotalDays=days)
        print("[OK]")
        return True
    except Exception as e:
        print(f"[X] {str(e)[:50]}")
        return False


def test_gold(symbol: str) -> dict:
    """Run Gold strategy on a symbol."""
    try:
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
        df = prepare_features(data_path)
        signals = generate_signals(df, config)

        if len(signals) == 0:
            return {"symbol": symbol, "trades": 0, "note": "No signals"}

        regime = daily_regime_table(df)
        tradeable = set(regime.loc[regime["regime_tradeable"], "date"])
        signals = signals[signals["date"].isin(tradeable)].copy()

        if len(signals) == 0:
            return {"symbol": symbol, "trades": 0, "note": "No regime signals"}

        strength = signal_strength_table(df, signals, config)
        signals = signals.merge(
            strength[["date", "direction", "signal_strength", "strength_trigger_component"]],
            on=["date", "direction"],
            how="left",
        )
        signals = signals[
            (signals["signal_strength"] >= 45) & (signals["strength_trigger_component"] >= 0.15)
        ].copy()

        if len(signals) == 0:
            return {"symbol": symbol, "trades": 0, "note": "No strength signals"}

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
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)[:80]}


def ask_groq(new_results: list) -> str:
    """Ask Groq to design the best portfolio."""
    if not GROQ_API_KEY:
        return "ERROR: No API key"

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=CONFIG.get("groq_base_url", "https://api.groq.com/openai/v1"),
            api_key=GROQ_API_KEY,
        )

        result_text = "\n".join(
            [
                f"- {r['symbol']}: Net={r.get('net_pct', 0):+.1f}%, PF={r.get('profit_factor', 0):.2f}, "
                f"WR={r.get('win_rate_pct', 0):.0f}%, DD={r.get('max_dd_pct', 0):.1f}%, Trades={r.get('trades', 0)}"
                for r in new_results
                if "net_pct" in r
            ]
        )

        prompt = f"""You are a quantitative trading researcher.

## New Stocks Tested with SUPER GOLD
{result_text}

## Previous Winners
- CGPOWER: +48.3%, PF 2.65, 72 trades
- BHEL: +6.2%, PF 2.72, 11 trades
- M&M: +2.7%, PF 1.28, 33 trades
- HCLTECH: +2.5%, PF 1.62, 14 trades
- TITAN: +2.4%, PF 1.81, 14 trades

## Context
- We trade VWAP-EMA pullbacks on 5-min data
- Regime filter: turnover > 1B, range > 2%
- Strength filter: score >= 45
- 8 stocks have proven profitable

## Task
1. Design a PORTFOLIO from profitable stocks (max 5 stocks)
2. Consider correlation (don't pick 2 highly correlated stocks)
3. Estimate PORTFOLIO return if you traded all
4. Suggest 3 more stocks to test

Format:
{{
    "portfolio": [{{"symbol": "X", "allocation": "N%", "reason": "why"}}],
    "estimated_return": "X%",
    "more_to_test": [{{"symbol": "X", "reason": "why"}}]
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
    print("EXPERIMENT 3: Download + Test New Candidates")
    print("=" * 60)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n")

    # Try to download new candidates
    print("Step 1: Downloading new candidates...")
    downloaded = []
    for sym in NEW_CANDIDATES:
        data_path = Path(f"Data/{sym}/{sym}_5MIN.csv")
        if data_path.exists():
            print(f"  {sym}: [Already have data]")
            downloaded.append(sym)
        else:
            print(f"  {sym}: ", end="")
            if download_data(sym):
                downloaded.append(sym)

    print(f"\nDownloaded: {downloaded}")

    # Test all new candidates
    print("\nStep 2: Testing new candidates with SUPER GOLD...")
    new_results = []
    for sym in downloaded:
        print(f"  {sym}...", end=" ")
        r = test_gold(sym)
        new_results.append(r)
        if "error" in r:
            print(f"[X] {r['error']}")
        elif "note" in r:
            print(f"[-] {r['note']}")
        else:
            print(
                f"[OK] Net: {r['net_pct']:+.1f}%, PF: {r['profit_factor']:.2f}, Trades: {r['trades']}"
            )

    # Sort by net return
    valid = sorted(
        [r for r in new_results if "net_pct" in r], key=lambda x: x["net_pct"], reverse=True
    )

    print("\n" + "=" * 60)
    print("NEW CANDIDATES RESULTS")
    print("=" * 60)
    print(f"{'Symbol':<15} {'Net%':>8} {'PF':>6} {'WR%':>6} {'DD%':>8} {'Trades':>7}")
    print("-" * 60)
    for r in valid:
        print(
            f"{r['symbol']:<15} {r['net_pct']:>+8.1f} {r['profit_factor']:>6.2f} "
            f"{r['win_rate_pct']:>6.1f} {r['max_dd_pct']:>8.1f} {r['trades']:>7}"
        )

    winners = [r for r in valid if r["net_pct"] > 0]
    print(f"\nNew winners: {len(winners)} / {len(valid)}")

    # Ask Groq for portfolio
    print("\n" + "=" * 60)
    print("GROQ PORTFOLIO DESIGN")
    print("=" * 60)
    analysis = ask_groq(new_results)
    print(analysis.encode("ascii", "replace").decode())

    # Save
    output_dir = Path("Research/GroqAnalysis")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(output_dir / f"exp03_{ts}.json", "w") as f:
        json.dump(
            {
                "experiment": "exp03_new_candidates",
                "timestamp": ts,
                "downloaded": downloaded,
                "results": new_results,
                "analysis": analysis,
            },
            f,
            indent=2,
        )

    print(f"\n[Saved] Research/GroqAnalysis/exp03_{ts}.json")


if __name__ == "__main__":
    main()
