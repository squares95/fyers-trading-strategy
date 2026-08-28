"""
Groq-Powered Strategy Analyzer

Uses Groq LLM (openai/gpt-oss-120b) to analyze trading strategy results
and generate insights for next experiments.

Run: python Research/groq_strategy_analyzer.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

# Import strategy

# Groq client
try:
    from openai import OpenAI
except ImportError:
    os.system("pip install openai")
    from openai import OpenAI


def get_groq_client():
    """Initialize Groq client."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Run: export GROQ_API_KEY='your_key'")

    return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)


def run_backtest(symbol: str, config_name: str = "SUPER_GOLD") -> dict:
    """Run backtest for a symbol."""
    print(f"\n{'='*60}")
    print(f"Running backtest: {symbol} with {config_name}")
    print(f"{'='*60}")

    try:
        # Get config
        if config_name == "SUPER_GOLD":
            from Strategies.G01.Gold import get_super_gold_config

            config = get_super_gold_config()
        elif config_name == "GOLD":
            from Strategies.G01.Gold import get_gold_config

            config = get_gold_config()
        else:
            from Strategies.G01.Gold import get_gold_config

            config = get_gold_config()

        # Run backtest using Gold.run() method

        # Check if data exists
        data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
        if not data_path.exists():
            return {"error": f"Data not found: {data_path}"}

        # Load data
        df = pd.read_csv(data_path, parse_dates=["datetime"])

        # Prepare features
        from Strategies.G01 import backtest, generate_signals, prepare_features, summarize_trades

        df = prepare_features(df, config)
        signals = generate_signals(df, config)
        trades = backtest(signals, config)
        stats = summarize_trades(trades)

        # Gold-specific: regime + strength filtering
        from Strategies.G01.Gold import (
            attach_signal_strength,
            daily_regime_table,
            filter_by_strength,
            filter_signals_by_regime,
        )

        regime = daily_regime_table(df)
        signals = filter_signals_by_regime(signals, regime)
        signals = attach_signal_strength(signals, df, config)
        signals = filter_by_strength(signals, min_strength=45)  # Adjustable
        trades_gold = backtest(signals, config)
        stats_gold = summarize_trades(trades_gold)

        return {
            "symbol": symbol,
            "config": config_name,
            "base_stats": stats,
            "gold_stats": stats_gold,
            "num_trades_base": len(trades),
            "num_trades_gold": len(trades_gold),
            "regime_stats": {
                "total_days": len(regime),
                "tradeable_days": len(regime[regime["tradeable"] == True]),
            },
        }

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def format_stats_for_llm(stats: dict) -> str:
    """Format backtest stats for LLM analysis."""
    if "error" in stats:
        return f"Error: {stats['error']}"

    s = stats.get("gold_stats", stats.get("base_stats", {}))

    return f"""
{symbol}: {stats['symbol']}
Config: {stats['config']}
---
Trades: {stats.get('num_trades_gold', stats.get('num_trades_base', 'N/A'))}
Net Return: {s.get('net_return', 'N/A'):.2%}" if isinstance(s.get('net_return'), float) else f"Net Return: {s.get('net_return', 'N/A')}"
Win Rate: {s.get('win_rate', 'N/A'):.1%}" if isinstance(s.get('win_rate'), float) else f"Win Rate: {s.get('win_rate', 'N/A')}"
Profit Factor: {s.get('profit_factor', 'N/A'):.3f}" if isinstance(s.get('profit_factor'), float) else f"Profit Factor: {s.get('profit_factor', 'N/A')}"
Max Drawdown: {s.get('max_drawdown', 'N/A'):.2%}" if isinstance(s.get('max_drawdown'), float) else f"Max Drawdown: {s.get('max_drawdown', 'N/A')}"
Avg Trade: {s.get('avg_trade', 'N/A'):.2f}%" if isinstance(s.get('avg_trade'), float) else f"Avg Trade: {s.get('avg_trade', 'N/A')}"
---
"""


def ask_groq_for_insights(results: list[dict], question: str = "") -> str:
    """Send results to Groq and get insights."""
    client = get_groq_client()

    # Format results
    results_text = "\n".join([format_stats_for_llm(r) for r in results])

    prompt = f"""You are an expert quantitative trading researcher analyzing backtest results.

## Backtest Results
{results_text}

## Strategy Context
- Strategy: VWAP-EMA Pullback (SUPER GOLD config)
- Timeframe: 5-minute candles
- Entry: Price touches EMA13/VWAP, recovers above
- Stop: 1.3x ATR
- Target: 3.9R (3.9x risk)
- Regime filter: Turnover > 1B, Range > 2%
- Strength filter: Score >= 45

## Known Successful Stocks
- CGPOWER: +47.54% net, 75 trades, PF 2.52
- BHEL: +6.81% net, 10 trades, PF 3.21

## Failed Stocks
TATAPOWER, ADANIPOWER, NTPC, POWERGRID (all power sector but didn't work)

## Your Task
{question or "Analyze these results. What do CGPOWER and BHEL have in common? What made TATAPOWER fail while CGPOWER succeeded? Suggest 3 specific next experiments to find more profitable stocks."}

Format your response as:
1. Key insights (bullet points)
2. Next 3 experiments (specific, actionable)
3. Any red flags or concerns
"""

    print("\n" + "=" * 60)
    print("SENDING TO GROQ...")
    print("=" * 60)

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": "You are an expert quantitative trading researcher. Be concise, specific, and actionable.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=1500,
        temperature=0.3,
    )

    return response.choices[0].message.content


def main():
    print("=" * 60)
    print("GROQ STRATEGY ANALYZER")
    print("=" * 60)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")

    # Check API key
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("\n⚠️  GROQ_API_KEY not set!")
        print("   Run: export GROQ_API_KEY='your_key'")
        return

    # Symbols to analyze
    symbols = ["CGPOWER", "BHEL"]

    # Run backtests
    results = []
    for symbol in symbols:
        result = run_backtest(symbol)
        results.append(result)
        print(json.dumps(result, indent=2, default=str)[:500] + "...")

    # Get Groq insights
    print("\n" + "=" * 60)
    print("ASKING GROQ FOR INSIGHTS...")
    print("=" * 60)

    insights = ask_groq_for_insights(results)

    print("\n" + "=" * 60)
    print("GROQ INSIGHTS")
    print("=" * 60)
    print(insights)

    # Save results
    output_dir = Path("Research/GroqAnalysis")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save raw results
    with open(output_dir / f"backtest_results_{timestamp}.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Save insights
    with open(output_dir / f"groq_insights_{timestamp}.txt", "w") as f:
        f.write("# Groq Strategy Analysis\n")
        f.write(f"# Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
        f.write(insights)

    print(f"\n✅ Results saved to {output_dir}/")
    print(f"   - backtest_results_{timestamp}.json")
    print(f"   - groq_insights_{timestamp}.txt")

    return insights


if __name__ == "__main__":
    insights = main()

    # Print just the insights for easy copying
    print("\n" + "=" * 60)
    print("INSIGHTS (copy below this line)")
    print("=" * 60)
    print(insights)
