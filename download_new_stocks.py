"""
Download new stock data for testing SUPER GOLD strategy.

This script downloads 5-min data for stocks that might work with our strategy.
Focus on high-volatility mid-cap stocks similar to CGPOWER.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Stocks to download - similar profile to CGPOWER
STOCKS_TO_TRY = [
    # Power sector (CGPOWER is power sector)
    "TATAPOWER",    # Tata Power
    "ADANIPOWER",   # Adani Power
    "NTPC",         # NTPC
    "POWERGRID",    # Power Grid
    "BHEL",         # Bharat Heavy Electricals

    # High beta mid-caps
    "TATAMOTORS",   # Tata Motors
    "MARUTI",       # Maruti Suzuki
    "ADANIENT",     # Adani Enterprises
    "JSWSTEEL",     # JSW Steel
    "TATASTEEL",    # Tata Steel

    # Banking (high volume)
    "HDFCBANK",     # Already have
    "ICICIBANK",    # Already have
    "KOTAKBANK",    # Kotak Mahindra
    "AXISBANK",     # Axis Bank

    # Volatile sectors
    "ADANIPORTS",   # Adani Ports
    "ONGC",         # ONGC
    "COALINDIA",    # Coal India
    "BPCL",         # BPCL
    "IOC",          # Indian Oil
]

def download_stock_data(symbol, days=400):
    """Download 5-min data for a stock."""
    try:
        import Main

        print(f"\nDownloading {symbol} ({days} days)...")
        result = Main.RunExample(
            "download",
            [symbol],
            downloadTotalDays=days,
            chunkDays=100,
            downloadStats=False
        )

        # Check if file was created
        data_path = Path(f"Data/{symbol}/{symbol}_5MIN.csv")
        if data_path.exists():
            file_size = data_path.stat().st_size / 1024  # KB
            print(f"SUCCESS: {symbol} downloaded ({file_size:.1f} KB)")
            return True
        else:
            print(f"FAILED: {symbol} - file not created")
            return False

    except Exception as e:
        print(f"ERROR: {symbol} - {e}")
        return False


def main():
    print("=" * 80)
    print("DOWNLOAD NEW STOCK DATA")
    print("=" * 80)
    print(f"\nStocks to try: {len(STOCKS_TO_TRY)}")
    print("\nNote: This requires Fyers API login.")
    print("Make sure you have valid credentials configured.\n")

    successful = []
    failed = []

    for symbol in STOCKS_TO_TRY:
        if download_stock_data(symbol):
            successful.append(symbol)
        else:
            failed.append(symbol)

    print("\n" + "=" * 80)
    print("DOWNLOAD SUMMARY")
    print("=" * 80)
    print(f"\nSuccessful: {len(successful)}/{len(STOCKS_TO_TRY)}")
    for s in successful:
        print(f"  [OK] {s}")

    if failed:
        print(f"\nFailed: {len(failed)}")
        for s in failed:
            print(f"  [FAIL] {s}")

    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("\n1. Run: py Research/find_profitable_stocks.py")
    print("2. This will test SUPER GOLD on the new stocks")
    print("3. Find which ones work with the strategy")


if __name__ == "__main__":
    main()
