"""
Fetch India VIX historical data using yfinance.
Saves to Data/INDIAVIX/INDIAVIX_1D.csv for use in regime filters.

Run: python Research/fetch_india_vix.py
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "Data" / "INDIAVIX"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "INDIAVIX_1D.csv"


def fetch_vix_yfinance() -> pd.DataFrame:
    """Use yfinance to download India VIX."""
    try:
        import yfinance as yf
    except ImportError:
        print("Installing yfinance...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "-q"])
        import yfinance as yf

    # India VIX ticker on Yahoo Finance
    ticker = yf.Ticker("^INDIAVIX")

    # Get 5 years of data
    end = datetime.now()
    start = end - timedelta(days=5 * 365)
    print(f"Downloading India VIX from {start.date()} to {end.date()}...")
    df = ticker.history(start=start, end=end, interval="1d")
    if df.empty:
        print("No data returned from yfinance")
        return pd.DataFrame()
    df = df.reset_index()
    # Normalize columns to match our format: Datetime, Open, High, Low, Close, Volume
    df = df.rename(columns={"Date": "Datetime", "Open": "Open", "High": "High",
                            "Low": "Low", "Close": "Close", "Volume": "Volume"})
    df["Datetime"] = pd.to_datetime(df["Datetime"]).dt.tz_localize(None)
    df = df[["Datetime", "Open", "High", "Low", "Close", "Volume"]]
    return df


def fetch_vix_nse_scrape() -> pd.DataFrame:
    """
    Fallback: try to scrape NSE India VIX historical.
    NSE's archive endpoint is public but rate-limited.
    """
    try:
        import requests
    except ImportError:
        print("requests not installed, skipping NSE scrape")
        return pd.DataFrame()

    # NSE historical data archive (e.g., for VIX, segment=FO, instrument=FUTIDX)
    # This is best-effort. If NSE blocks, fall back to yfinance.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    print("Trying NSE scrape (may be blocked)...")
    try:
        # NSE historical data endpoint
        url = "https://www.nseindia.com/api/historical/indicesHistory"
        params = {
            "indexType": "INDIA VIX",
            "fromDate": (datetime.now() - timedelta(days=365 * 5)).strftime("%d-%m-%Y"),
            "toDate": datetime.now().strftime("%d-%m-%Y"),
        }
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if "data" in data and data["data"]:
                df = pd.DataFrame(data["data"])
                df = df.rename(columns={"EOD_TIMESTAMP": "Datetime",
                                        "EOD_OPEN_INDEX_VAL": "Open",
                                        "EOD_HIGH_INDEX_VAL": "High",
                                        "EOD_LOW_INDEX_VAL": "Low",
                                        "EOD_CLOSE_INDEX_VAL": "Close"})
                df["Datetime"] = pd.to_datetime(df["Datetime"])
                df["Volume"] = 0  # VIX has no volume
                return df[["Datetime", "Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        print(f"NSE scrape failed: {e}")
    return pd.DataFrame()


def main():
    # Try yfinance first (most reliable for free)
    df = fetch_vix_yfinance()
    if df.empty:
        print("Trying NSE scrape fallback...")
        df = fetch_vix_nse_scrape()
    if df.empty:
        print("[!] Could not fetch VIX data. Will use synthetic VIX proxy from BANKNIFTY realized vol.")
        return

    df = df.sort_values("Datetime").reset_index(drop=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"[Saved] {OUT_PATH}  ({len(df)} rows, {df['Datetime'].min().date()} to {df['Datetime'].max().date()})")
    print(f"Latest VIX: {df.iloc[-1]['Close']:.2f}")


if __name__ == "__main__":
    main()
