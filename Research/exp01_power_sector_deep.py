"""
Experiment 1: Power Sector Deep Dive
Hypothesis: Specific characteristics distinguish working power stocks from failing ones.

This script:
1. Runs SUPER GOLD on all available power sector stocks
2. Extracts characteristics (volatility, turnover, ATR%, regime tradeability %)
3. Asks Groq to find patterns
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

# Power sector symbols (with available data)
POWER_STOCKS = [
    "CGPOWER",  # Known winner
    "BHEL",     # Known winner
    "TATAPOWER",   # Known loser
    "ADANIPOWER",  # Known loser
    "NTPC",        # Known loser
    "POWERGRID",   # Known loser
    "SUZLON",      # Known loser (but renewable)
]


def load_and_analyze_symbol(symbol: str) -> dict:
    """Load data and extract characteristics without running strategy."""
    data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")

    if not data_path.exists():
        return {"symbol": symbol, "error": f"No data: {data_path}"}

    try:
        df = pd.read_csv(data_path, parse_dates=['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)

        # Basic stats
        df['date'] = df['datetime'].dt.date
        daily = df.groupby('date').agg({
            'close': 'last',
            'high': 'max',
            'low': 'min',
            'volume': 'sum'
        }).reset_index()

        daily['turnover'] = daily['close'] * daily['volume']
        daily['range_pct'] = (daily['high'] - daily['low']) / daily['low'] * 100
        daily['return_pct'] = daily['close'].pct_change() * 100
        daily['intraday_vol'] = (daily['high'] - daily['low']) / daily['open'] * 100 if 'open' in daily.columns else daily['range_pct']

        # Intraday volatility (avg 5-min move)
        df['5min_return'] = df['close'].pct_change()
        intraday_vol = df['5min_return'].std() * 100

        # Characteristic extraction
        result = {
            "symbol": symbol,
            "data_days": len(daily),
            "avg_volume": int(daily['volume'].mean()),
            "avg_turnover_cr": round(daily['turnover'].mean() / 1e7, 2),  # In crores
            "avg_daily_range_pct": round(daily['range_pct'].mean(), 3),
            "med_daily_range_pct": round(daily['range_pct'].median(), 3),
            "avg_intraday_vol_pct": round(daily['intraday_vol'].mean(), 3),
            "avg_5min_vol_pct": round(intraday_vol, 4),
            "return_volatility": round(daily['return_pct'].std(), 3),
            "avg_daily_return": round(daily['return_pct'].mean(), 4),
            "max_drawdown_pct": round(((daily['close'] / daily['close'].cummax()) - 1).min() * 100, 2),
            "positive_days_pct": round((daily['return_pct'] > 0).sum() / len(daily) * 100, 1),
            "high_turnover_days_pct": round((daily['turnover'] > 1e9).sum() / len(daily) * 100, 1),  # > 1000 cr
            "high_range_days_pct": round((daily['range_pct'] > 2).sum() / len(daily) * 100, 1),  # > 2%
        }
        return result

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def run_strategy_quick(symbol: str) -> dict:
    """Run SUPER GOLD strategy and return key stats."""
    data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
    if not data_path.exists():
        return {"symbol": symbol, "error": "No data"}

    try:
        from Strategies.G01.Gold import (
            get_super_gold_config, prepare_features, generate_signals,
            backtest, summarize_trades, daily_regime_table,
            filter_signals_by_regime, attach_signal_strength, filter_by_strength
        )

        config = get_super_gold_config()
        df = pd.read_csv(data_path, parse_dates=['datetime'])

        df = prepare_features(df, config)
        signals = generate_signals(df, config)

        # Apply regime + strength filters
        regime = daily_regime_table(df)
        signals = filter_signals_by_regime(signals, regime)
        signals = attach_signal_strength(signals, df, config)
        signals = filter_by_strength(signals, min_strength=45)

        trades = backtest(signals, config)
        stats = summarize_trades(trades)

        if not stats or len(trades) == 0:
            return {
                "symbol": symbol,
                "net_return_pct": 0.0,
                "trades": 0,
                "note": "No qualifying trades"
            }

        return {
            "symbol": symbol,
            "net_return_pct": round(stats.get('net_return', 0) * 100, 2),
            "profit_factor": round(stats.get('profit_factor', 0), 3),
            "win_rate_pct": round(stats.get('win_rate', 0) * 100, 1),
            "max_dd_pct": round(stats.get('max_drawdown', 0) * 100, 2),
            "trades": len(trades),
            "avg_trade_pct": round(stats.get('avg_trade', 0) * 100, 3)
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def ask_groq_for_patterns(characteristics: list, results: list) -> str:
    """Ask Groq to find patterns."""
    try:
        from openai import OpenAI
    except ImportError:
        os.system("pip install openai")
        from openai import OpenAI

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "ERROR: GROQ_API_KEY not set"

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key
    )

    # Format data
    char_text = "\n".join([json.dumps(c, indent=2) for c in characteristics])
    result_text = "\n".join([json.dumps(r, indent=2) for r in results])

    prompt = f"""You are a quantitative researcher. I'm trying to find a screen for profitable trading setups.

## Stock Characteristics
{char_text}

## Strategy Results (SUPER GOLD - VWAP-EMA Pullback)
{result_text}

## Context
- Known winners: CGPOWER, BHEL
- Known losers: TATAPOWER, ADANIPOWER, NTPC, POWERGRID, SUZLON
- All in power sector but vastly different results

## Your Task
1. Identify the 3-5 characteristics that DISTINGUISH winners from losers
2. Give specific thresholds (e.g., "intraday_vol > 0.5%")
3. Suggest 5 NEW stock candidates I should download data for
4. Be specific - I need concrete numbers to filter on

Format response as JSON:
{{
    "discriminating_features": [{{"feature": "...", "winner_range": "...", "loser_range": "...", "threshold": "..."}}],
    "screen_rules": ["rule1", "rule2", ...],
    "new_candidates": [{{"symbol": "...", "reason": "..."}}, ...]
}}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": "You are a quantitative researcher. Output strict JSON only."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=2000,
        temperature=0.2
    )

    return response.choices[0].message.content


def main():
    print("="*60)
    print("EXPERIMENT 1: Power Sector Deep Dive")
    print("="*60)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n")

    # Check API key
    if not os.environ.get("GROQ_API_KEY"):
        print("⚠️  GROQ_API_KEY not set!")
        return

    # Step 1: Extract characteristics
    print("Step 1: Extracting stock characteristics...")
    characteristics = []
    for symbol in POWER_STOCKS:
        print(f"  - {symbol}...", end=" ")
        chars = load_and_analyze_symbol(symbol)
        characteristics.append(chars)
        if "error" in chars:
            print(f"❌ {chars['error']}")
        else:
            print(f"✓ ({chars['data_days']} days)")

    # Step 2: Run strategy
    print("\nStep 2: Running SUPER GOLD strategy...")
    results = []
    for symbol in POWER_STOCKS:
        print(f"  - {symbol}...", end=" ")
        result = run_strategy_quick(symbol)
        results.append(result)
        if "error" in result:
            print(f"❌ {result['error']}")
        elif "note" in result:
            print(f"⊘ {result['note']}")
        else:
            print(f"✓ Net: {result['net_return_pct']}%, Trades: {result['trades']}")

    # Step 3: Ask Groq
    print("\nStep 3: Asking Groq for patterns...")
    analysis = ask_groq_for_patterns(characteristics, results)

    print("\n" + "="*60)
    print("GROQ ANALYSIS")
    print("="*60)
    print(analysis)

    # Save results
    output_dir = Path("Research/GroqAnalysis")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(output_dir / f"exp01_power_sector_{timestamp}.json", "w") as f:
        json.dump({
            "characteristics": characteristics,
            "results": results,
            "groq_analysis": analysis
        }, f, indent=2, default=str)

    print(f"\n✅ Saved to {output_dir}/exp01_power_sector_{timestamp}.json")

    return analysis


if __name__ == "__main__":
    analysis = main()
    if analysis:
        print("\n" + "="*60)
        print("COPY GROQ ANALYSIS BELOW")
        print("="*60)
        print(analysis)