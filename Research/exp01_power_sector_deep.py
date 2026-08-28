"""
Experiment 1: Power Sector Deep Dive
Uses existing Gold.run() for CGPOWER + Core for other stocks.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# CONFIG LOADER
# ============================================================================


def load_config() -> dict:
    config_path = Path("Config/groq_config.json")
    if not config_path.exists():
        print(f"[X] Config not found: {config_path}")
        return {}
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"[X] Error reading config: {e}")
        return {}


CONFIG = load_config()
GROQ_API_KEY = CONFIG.get("groq_api_key", "")


# Power sector symbols
POWER_STOCKS = ["CGPOWER", "BHEL", "TATAPOWER", "ADANIPOWER", "NTPC", "POWERGRID", "SUZLON"]


def get_stock_characteristics(symbol: str) -> dict:
    """Extract characteristics from CSV."""
    data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
    if not data_path.exists():
        return {"symbol": symbol, "error": "No data"}

    try:
        df = pd.read_csv(data_path)
        dt_col = next((c for c in ["Datetime", "datetime", "date"] if c in df.columns), None)
        if not dt_col:
            return {"symbol": symbol, "error": "No datetime col"}
        df = df.rename(columns={dt_col: "Datetime"})
        df["Datetime"] = pd.to_datetime(df["Datetime"])
        df = df.sort_values("Datetime").reset_index(drop=True)

        df["date"] = df["Datetime"].dt.date
        daily = (
            df.groupby("date")
            .agg({"Close": "last", "High": "max", "Low": "min", "Open": "first", "Volume": "sum"})
            .reset_index()
        )

        daily["range_pct"] = (daily["High"] - daily["Low"]) / daily["Low"] * 100
        daily["return_pct"] = daily["Close"].pct_change()

        df["5min_ret"] = df["Close"].pct_change()

        return {
            "symbol": symbol,
            "data_days": len(daily),
            "avg_5min_vol": round(df["5min_ret"].std() * 100, 4),
            "avg_daily_range": round(daily["range_pct"].mean(), 3),
            "return_vol": round(daily["return_pct"].std(), 3),
            "high_range_days_pct": round((daily["range_pct"] > 2).sum() / len(daily) * 100, 1),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def run_gold_strategy(symbol: str) -> dict:
    """Run SUPER GOLD via existing Gold.run() or Core strategy."""
    data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
    if not data_path.exists():
        return {"symbol": symbol, "error": "No data", "net_return_pct": 0}

    try:
        # Use Core.run_strategy for quick backtest
        from Strategies.G01.Core import run_strategy, summarize_trades

        _, _, trades = run_strategy(path=str(data_path))

        if trades is None or len(trades) == 0:
            return {"symbol": symbol, "trades": 0, "note": "No trades"}

        stats = summarize_trades(trades)
        return {
            "symbol": symbol,
            "net_return_pct": round(stats.get("net_pct", 0), 2),
            "profit_factor": round(stats.get("profit_factor", 0), 3),
            "win_rate_pct": round(stats.get("win_rate_pct", 0), 1),
            "max_dd_pct": round(stats.get("max_dd_pct", 0), 2),
            "trades": len(trades),
            "avg_bps": round(stats.get("avg_bps", 0), 2),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def ask_groq(chars: list, results: list) -> str:
    """Get insights from Groq."""
    try:
        from openai import OpenAI
    except ImportError:
        return "ERROR: openai not installed"

    if not GROQ_API_KEY:
        return "ERROR: GROQ_API_KEY not set"

    client = OpenAI(
        base_url=CONFIG.get("groq_base_url", "https://api.groq.com/openai/v1"), api_key=GROQ_API_KEY
    )

    char_text = "\n".join([json.dumps(c, indent=2) for c in chars])
    result_text = "\n".join([json.dumps(r, indent=2) for r in results])

    prompt = f"""You are a quantitative researcher. Analyze this trading strategy data.

## Stock Characteristics
{char_text}

## Strategy Results
{result_text}

## Known: CGPOWER works (+47%), BHEL works (+6.81%), others don't.

## Task:
1. What distinguishes winners from losers?
2. Find 3-5 screen rules (specific numbers)
3. Suggest 5 new stocks to test

Format:
{{
    "insight": "One sentence",
    "rules": ["rule1", "rule2"],
    "candidates": [{{"symbol": "X", "reason": "why"}}]
}}
"""

    try:
        response = client.chat.completions.create(
            model=CONFIG.get("default_model", "openai/gpt-oss-120b"),
            messages=[
                {
                    "role": "system",
                    "content": "You are a quantitative researcher. Output strict JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.2,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ERROR: {e!s}"


def main():
    print("=" * 60)
    print("EXPERIMENT 1: Power Sector Deep Dive")
    print("=" * 60)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n")

    if not GROQ_API_KEY:
        print("[!] GROQ_API_KEY not set in Config/groq_config.json")
        return

    # Step 1: Characteristics
    print("Step 1: Extracting characteristics...")
    chars = []
    for sym in POWER_STOCKS:
        print(f"  {sym}...", end=" ")
        c = get_stock_characteristics(sym)
        chars.append(c)
        if "error" in c:
            print(f"[X] {c['error']}")
        else:
            print(f"[OK] vol={c['avg_5min_vol']}%, range={c['avg_daily_range']}%")

    # Step 2: Strategy results
    print("\nStep 2: Running strategy...")
    results = []
    for sym in POWER_STOCKS:
        print(f"  {sym}...", end=" ")
        r = run_gold_strategy(sym)
        results.append(r)
        if "error" in r:
            print(f"[X] {r['error']}")
        elif "note" in r:
            print(f"[-] {r['note']}")
        else:
            print(f"[OK] Net: {r['net_return_pct']:+.1f}%, PF: {r['profit_factor']:.2f}")

    # Step 3: Groq
    print("\nStep 3: Asking Groq...")
    analysis = ask_groq(chars, results)

    print("\n" + "=" * 60)
    print("GROQ ANALYSIS")
    print("=" * 60)
    print(analysis.encode("ascii", "replace").decode())

    # Save
    output_dir = Path("Research/GroqAnalysis")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(output_dir / f"exp01_{ts}.json", "w") as f:
        json.dump({"chars": chars, "results": results, "analysis": analysis}, f, indent=2)

    print(f"\n[Saved] Research/GroqAnalysis/exp01_{ts}.json")


if __name__ == "__main__":
    main()
