"""
Experiment 4: Portfolio Backtest
Simulates trading multiple stocks simultaneously with the SUPER GOLD strategy.
Tests if portfolio diversification improves risk-adjusted returns.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

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


# Portfolio: top profitable stocks from experiments 1-3
PORTFOLIO_STOCKS = [
    "CGPOWER",   # +48.3%, PF 2.65, 72 trades
    "BHEL",      # +6.2%, PF 2.72, 11 trades
    "DRREDDY",   # +6.7%, PF 2.24, 20 trades ⭐ NEW
    "INDUSINDBK", # +4.2%, PF 1.90, 16 trades ⭐ NEW
    "M&M",       # +2.7%, PF 1.28, 33 trades
    "HCLTECH",   # +2.5%, PF 1.62, 14 trades
    "TITAN",     # +2.4%, PF 1.81, 14 trades
]


def run_gold_single(symbol: str) -> dict:
    """Run Gold strategy on a single stock, return individual trades."""
    try:
        from Strategies.G01.features import prepare_features
        from Strategies.G01.signals import generate_signals
        from Strategies.G01.backtest import backtest
        from Strategies.G01.regime_filter import daily_regime_table
        from Strategies.G01.strength_scorer import signal_strength_table
        from Strategies.G01.Gold import get_super_gold_config

        data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
        if not data_path.exists():
            return {"symbol": symbol, "error": "No data", "trades": pd.DataFrame()}

        config = get_super_gold_config()
        df = prepare_features(data_path)
        signals = generate_signals(df, config)

        if len(signals) == 0:
            return {"symbol": symbol, "trades": pd.DataFrame()}

        regime = daily_regime_table(df)
        tradeable = set(regime.loc[regime["regime_tradeable"], "date"])
        signals = signals[signals["date"].isin(tradeable)].copy()

        if len(signals) == 0:
            return {"symbol": symbol, "trades": pd.DataFrame()}

        strength = signal_strength_table(df, signals, config)
        signals = signals.merge(
            strength[['date', 'direction', 'signal_strength', 'strength_trigger_component']],
            on=['date', 'direction'], how='left'
        )
        signals = signals[
            (signals['signal_strength'] >= 45) &
            (signals['strength_trigger_component'] >= 0.15)
        ].copy()

        if len(signals) == 0:
            return {"symbol": symbol, "trades": pd.DataFrame()}

        trades = backtest(df, signals, config)

        # Add symbol column
        trades['symbol'] = symbol

        return {"symbol": symbol, "trades": trades}

    except Exception as e:
        return {"symbol": symbol, "error": str(e)[:80], "trades": pd.DataFrame()}


def calculate_portfolio_metrics(trades_list: list) -> dict:
    """Calculate portfolio-level metrics from combined trades."""
    all_trades = pd.concat([t['trades'] for t in trades_list if len(t['trades']) > 0], ignore_index=True)

    if len(all_trades) == 0:
        return {"error": "No trades"}

    # Portfolio metrics (net_return is in decimal, e.g., 0.025 = 2.5%)
    all_trades['net_return_pct'] = all_trades['net_return'] * 100  # Convert to %

    total_return = all_trades['net_return_pct'].sum()
    win_trades = all_trades[all_trades['net_return'] > 0]
    loss_trades = all_trades[all_trades['net_return'] <= 0]

    gross_profit = win_trades['net_return_pct'].sum() if len(win_trades) > 0 else 0
    gross_loss = abs(loss_trades['net_return_pct'].sum()) if len(loss_trades) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    win_rate = len(win_trades) / len(all_trades) * 100

    # Max drawdown (portfolio level)
    all_trades = all_trades.sort_values('entry_time')
    cumulative = all_trades.groupby('entry_time')['net_return_pct'].sum().cumsum()
    peak = cumulative.cummax()
    drawdown = (cumulative - peak)
    max_dd = drawdown.min()

    # Monthly returns
    all_trades['month'] = pd.to_datetime(all_trades['entry_time']).dt.to_period('M')
    monthly = all_trades.groupby('month')['net_return_pct'].sum()

    return {
        "total_trades": int(len(all_trades)),
        "net_return_pct": round(total_return, 2),
        "profit_factor": round(profit_factor, 3),
        "win_rate_pct": round(win_rate, 1),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_trade_pct": round(all_trades['net_return_pct'].mean(), 3),
        "gross_profit_pct": round(gross_profit, 2),
        "gross_loss_pct": round(gross_loss, 2),
        "avg_winner_pct": round(win_trades['net_return_pct'].mean(), 3) if len(win_trades) > 0 else 0,
        "avg_loser_pct": round(loss_trades['net_return_pct'].mean(), 3) if len(loss_trades) > 0 else 0,
        "months_traded": int(len(monthly)),
        "profitable_months": int((monthly > 0).sum()),
        "monthly_avg": round(float(monthly.mean()), 3),
    }


def main():
    print("="*60)
    print("EXPERIMENT 4: Portfolio Backtest")
    print("="*60)
    print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Portfolio: {PORTFOLIO_STOCKS}\n")

    # Run Gold on each stock
    print("Step 1: Running SUPER GOLD on portfolio stocks...")
    trades_list = []
    individual_results = []

    for sym in PORTFOLIO_STOCKS:
        print(f"  {sym}...", end=" ")
        result = run_gold_single(sym)
        trades_list.append(result)
        if "error" in result:
            print(f"[X] {result['error']}")
        elif len(result['trades']) == 0:
            print(f"[-] No trades")
        else:
            net = result['trades']['net_return'].sum() * 100  # Convert to %
            print(f"[OK] {len(result['trades'])} trades, Net: {net:+.1f}%")
            individual_results.append({
                "symbol": sym,
                "trades": int(len(result['trades'])),
                "net_return_pct": round(net, 2),
                "win_rate_pct": round((result['trades']['net_return'] > 0).mean() * 100, 1),
            })

    # Calculate portfolio metrics
    print("\nStep 2: Calculating portfolio metrics...")
    portfolio_metrics = calculate_portfolio_metrics(trades_list)

    # Print individual results
    print("\n" + "="*60)
    print("INDIVIDUAL STOCK RESULTS")
    print("="*60)
    print(f"{'Symbol':<15} {'Trades':>7} {'Net%':>8} {'WinRate%':>10}")
    print("-"*60)
    for r in individual_results:
        print(f"{r['symbol']:<15} {r['trades']:>7} {r['net_return_pct']:>+8.1f} {r['win_rate_pct']:>10.1f}")
    total_individual = sum(r['net_return_pct'] for r in individual_results)
    print("-"*60)
    print(f"{'TOTAL (sum)':<15} {sum(r['trades'] for r in individual_results):>7} {total_individual:>+8.1f}")

    # Print portfolio results
    print("\n" + "="*60)
    print("PORTFOLIO RESULTS")
    print("="*60)
    print(f"  Total Trades:        {portfolio_metrics['total_trades']}")
    print(f"  Net Return:          {portfolio_metrics['net_return_pct']:+.1f}%")
    print(f"  Profit Factor:       {portfolio_metrics['profit_factor']:.3f}")
    print(f"  Win Rate:            {portfolio_metrics['win_rate_pct']:.1f}%")
    print(f"  Max Drawdown:        {portfolio_metrics['max_drawdown_pct']:.2f}%")
    print(f"  Avg Trade:           {portfolio_metrics['avg_trade_pct']:.3f}%")
    print(f"  Avg Winner:          {portfolio_metrics['avg_winner_pct']:.3f}%")
    print(f"  Avg Loser:           {portfolio_metrics['avg_loser_pct']:.3f}%")
    print(f"  Months Traded:       {portfolio_metrics['months_traded']}")
    print(f"  Profitable Months:   {portfolio_metrics['profitable_months']}/{portfolio_metrics['months_traded']}")
    print(f"  Monthly Avg Return:   {portfolio_metrics['monthly_avg']:.3f}%")

    # Risk metrics
    print("\n" + "="*60)
    print("RISK METRICS")
    print("="*60)
    all_trades = pd.concat([t['trades'] for t in trades_list if len(t['trades']) > 0], ignore_index=True)
    all_trades['net_return_pct'] = all_trades['net_return'] * 100
    monthly_returns = all_trades.groupby(pd.to_datetime(all_trades['entry_time']).dt.to_period('M'))['net_return_pct'].sum()

    monthly_std = monthly_returns.std()
    monthly_avg = portfolio_metrics['monthly_avg']

    print(f"  Annualized Return:   {monthly_avg * 12:.1f}%")
    print(f"  Monthly Std Dev:     {monthly_std:.3f}%")
    print(f"  Sharpe-like Ratio:   {monthly_avg / monthly_std:.2f}" if monthly_std > 0 else "  Sharpe-like Ratio:   N/A")

    # Save results
    output_dir = Path("Research/GroqAnalysis")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    results = {
        "experiment": "exp04_portfolio_backtest",
        "timestamp": ts,
        "portfolio": PORTFOLIO_STOCKS,
        "individual_results": individual_results,
        "portfolio_metrics": portfolio_metrics,
    }

    with open(output_dir / f"exp04_{ts}.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n[Saved] Research/GroqAnalysis/exp04_{ts}.json")

    return results


if __name__ == "__main__":
    main()