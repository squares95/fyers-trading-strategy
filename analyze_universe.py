import os

import pandas as pd

DATA_DIR = r"C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data"

print("=" * 80)
print("CROSS-SYMBOL DATA QUALITY (1-MIN)")
print("=" * 80)

# Focus on top-priority symbols for the universe
symbols = [
    "CGPOWER",
    "HDFCBANK",
    "NIFTY",
    "BANKNIFTY",
    "SBIN",
    "RELIANCE",
    "TCS",
    "INFY",
    "ICICIBANK",
    "BHARTIARTL",
    "M&M",
    "LT",
    "SUZLON",
    "BAJFINANCE",
    "BEL",
    "HCLTECH",
    "TITAN",
    "MIDCAP150_TRI",
    "SMALLCAP250_TRI",
    "HDFCSML250",
    "MIDCAPIETF",
]

summary = []
for sym in symbols:
    path = os.path.join(DATA_DIR, sym, f"{sym}_1MIN.csv")
    if not os.path.exists(path):
        summary.append({"Symbol": sym, "Status": "FILE NOT FOUND"})
        continue

    df = pd.read_csv(path, parse_dates=["Datetime"])
    df["date"] = df["Datetime"].dt.date
    df["time"] = df["Datetime"].dt.time

    daily_counts = df.groupby("date").size()
    after_hours = df[df["Datetime"].dt.time > pd.Timestamp("15:30:00").time()]
    pre_market = df[df["Datetime"].dt.time < pd.Timestamp("09:15:00").time()]

    # OHLC violations
    df["max_ocl"] = df[["Open", "Close", "Low"]].max(axis=1)
    df["min_och"] = df[["Open", "Close", "High"]].min(axis=1)
    ohlc_violations = ((df["High"] < df["max_ocl"]) | (df["Low"] > df["min_och"])).sum()

    summary.append(
        {
            "Symbol": sym,
            "Rows": len(df),
            "Days": len(daily_counts),
            "Start": str(df["Datetime"].min())[:10],
            "End": str(df["Datetime"].max())[:10],
            "Complete_375": f"{(daily_counts == 375).sum()}/{len(daily_counts)}",
            "AfterHours": len(after_hours),
            "PreMarket": len(pre_market),
            "OHLC_Violations": ohlc_violations,
        }
    )

result = pd.DataFrame(summary)
print(result.to_string(index=False))
print("\n" + "=" * 80)
