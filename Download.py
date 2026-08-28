import os
from datetime import date, timedelta

import pandas as pd

try:
    from tqdm import tqdm
except ImportError:

    class tqdm:  # type: ignore
        def __init__(self, iterable=None, **kwargs):
            self.iterable = iterable if iterable is not None else range(kwargs.get("total", 0))
            self.n = 0

        def __iter__(self):
            return iter(self.iterable)

        def update(self, n=1):
            self.n += n

        def close(self):
            pass

        @staticmethod
        def write(message):
            print(message)


from zoneinfo import ZoneInfo

try:
    import ta
except ImportError:
    ta = None
import time
from datetime import datetime

RAW_COLUMNS = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
FINAL_COLUMNS = RAW_COLUMNS + ["EMA9", "EMA21", "ADX", "ATR"]
EMA_FAST_WINDOW = 9
EMA_SLOW_WINDOW = 21
ADX_WINDOW = 14
ATR_WINDOW = 21
MIN_TA_INDICATOR_ROWS = max(EMA_SLOW_WINDOW, ATR_WINDOW, ADX_WINDOW * 2 + 1)
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:25"
MARKET_CLOSE_1MIN = "15:29"
EXPECTED_1MIN_BARS_PER_DAY = 375
EXPECTED_5MIN_BARS_PER_DAY = 75
HISTORY_INTRADAY_MAX_DAYS = 100
FYERS_BASE_RESOLUTION = "1"
TIMEFRAME_WRITE_STEPS = 5
TIMEFRAME_1MIN = "1MIN"
TIMEFRAME_5MIN = "5MIN"
TIMEFRAME_15MIN = "15MIN"
TIMEFRAME_1D = "1D"
TIMEFRAME_1W = "1W"
FYERS_SYMBOL_ALIASES = {
    "NIFTY": "NSE:NIFTY50-INDEX",
    "NIFTY50": "NSE:NIFTY50-INDEX",
    "NIFTY50-INDEX": "NSE:NIFTY50-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "NIFTYBANK": "NSE:NIFTYBANK-INDEX",
    "NIFTYBANK-INDEX": "NSE:NIFTYBANK-INDEX",
}


class FyersRateLimitError(RuntimeError):
    def __init__(self, symbol: str, range_start: date, range_end: date, response: dict):
        self.symbol = symbol
        self.range_start = range_start
        self.range_end = range_end
        self.response = response
        message = response.get("message", "request limit reached")
        super().__init__(f"{symbol} {range_start} to {range_end}: {message}")


def login():
    from Login import login as fyers_login

    return fyers_login()


def resolve_fyers_symbol(symbol: str) -> str:
    value = str(symbol).strip().upper()
    if not value:
        raise ValueError("Symbol cannot be empty")
    if ":" in value:
        return value
    if value in FYERS_SYMBOL_ALIASES:
        return FYERS_SYMBOL_ALIASES[value]
    if value.endswith("-INDEX"):
        return f"NSE:{value}"
    return f"NSE:{value}-EQ"


def fetchSymbols(key=None):
    from CFGFunctions import fetchSymbols as cfg_fetch_symbols

    return cfg_fetch_symbols(key)


def isMarketOpen(fyers):
    response = fyers.market_status()

    status = next(
        (
            item["status"]
            for item in response["marketStatus"]
            if item["exchange"] == 10 and item["segment"] == 11
        ),
        None,
    )
    return status


def checkLastCandle(symbol: str, path: str = "Data") -> datetime:
    file_path = base_1min_input_path(symbol, path)
    df = pd.read_csv(file_path, parse_dates=["Datetime"])
    return df.iloc[-1]["Datetime"]


def UpdateCSV(symbol: str, fyers, path: str = "Data") -> bool:
    """
    Checks if the CSV file for the symbol is up to date.
    If not, fetches missing 1-minute candles from Fyers and appends to the file.

    Returns:
        bool: True if CSV was updated, False if already up to date or market closed.
    """
    if not isMarketOpen(fyers):
        print("Market is closed.")
        return False

    ist = ZoneInfo("Asia/Kolkata")
    file_path = base_1min_input_path(symbol, path)

    # Get last datetime from CSV
    last_dt = checkLastCandle(symbol, path)

    # Round current time down to the latest complete minute
    now = datetime.now(ist).replace(second=0, microsecond=0, tzinfo=None)

    if last_dt >= now:
        # print("CSV already up to date.")
        return False

    fyers_symbol = resolve_fyers_symbol(symbol)

    # Fyers API requires timestamps in seconds
    from_time = int((last_dt + timedelta(minutes=1)).replace(tzinfo=ist).timestamp())
    to_time = int(now.replace(tzinfo=ist).timestamp())

    response = fyers.history(
        {
            "symbol": fyers_symbol,
            "resolution": FYERS_BASE_RESOLUTION,
            "date_format": "0",
            "range_from": from_time,
            "range_to": to_time,
            "cont_flag": "1",
        }
    )

    if "candles" not in response or not response["candles"]:
        print("No new candles available.")
        return False

    new_data = candles_to_dataframe(response["candles"], ZoneInfo("Asia/Kolkata"))
    existing_df = read_existing_candles(file_path)
    merged = normalize_candles(pd.concat([existing_df, new_data], ignore_index=True))
    output = write_timeframe_files(symbol, path, merged)
    print(
        f"Appended {len(new_data)} new candles to {symbol}; "
        f"saved {output['rows'][TIMEFRAME_1MIN]} 1MIN rows and "
        f"{output['rows'][TIMEFRAME_5MIN]} 5MIN rows."
    )
    return True


def normalize_candles(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=RAW_COLUMNS)

    df = df[RAW_COLUMNS].copy()
    df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=RAW_COLUMNS)
    df = df.drop_duplicates("Datetime", keep="last")
    df = df.sort_values("Datetime").reset_index(drop=True)
    return df


def symbol_data_folder(symbol: str, output_folder: str) -> str:
    return os.path.join(output_folder, symbol)


def timeframe_file_path(symbol: str, output_folder: str, timeframe: str) -> str:
    return os.path.join(symbol_data_folder(symbol, output_folder), f"{symbol}_{timeframe}.csv")


def legacy_symbol_file_path(symbol: str, output_folder: str) -> str:
    return os.path.join(output_folder, f"{symbol}.csv")


def base_1min_input_path(symbol: str, output_folder: str) -> str:
    return timeframe_file_path(symbol, output_folder, TIMEFRAME_1MIN)


def preferred_5min_input_path(symbol: str, output_folder: str) -> str:
    new_path = timeframe_file_path(symbol, output_folder, TIMEFRAME_5MIN)
    if os.path.exists(new_path):
        return new_path
    return legacy_symbol_file_path(symbol, output_folder)


def read_existing_base_candles(symbol: str, output_folder: str) -> pd.DataFrame:
    file_path = base_1min_input_path(symbol, output_folder)
    if not os.path.exists(file_path):
        return pd.DataFrame(columns=RAW_COLUMNS)
    return read_existing_candles(file_path)


def read_existing_candles(file_path: str) -> pd.DataFrame:
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return pd.DataFrame(columns=RAW_COLUMNS)

    df = pd.read_csv(file_path, parse_dates=["Datetime"])
    missing_columns = [col for col in RAW_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(f"{file_path} is missing columns: {missing_columns}")

    df = df[RAW_COLUMNS].copy()
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    return normalize_candles(df)


def candles_to_dataframe(candles, ist: ZoneInfo) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=RAW_COLUMNS)

    valid_candles = [
        candle[:6] for candle in candles if isinstance(candle, (list, tuple)) and len(candle) >= 6
    ]
    if not valid_candles:
        return pd.DataFrame(columns=RAW_COLUMNS)

    df = pd.DataFrame(valid_candles, columns=["epoch", "Open", "High", "Low", "Close", "Volume"])
    df["epoch"] = pd.to_numeric(df["epoch"], errors="coerce")
    df["Datetime"] = pd.to_datetime(df["epoch"], unit="s", utc=True, errors="coerce")
    df["Datetime"] = df["Datetime"].dt.tz_convert(ist).dt.tz_localize(None)
    return normalize_candles(df[RAW_COLUMNS])


def missing_date_ranges(
    existing_df: pd.DataFrame,
    start_date: date,
    end_date: date,
    expected_bars_per_day: int = EXPECTED_1MIN_BARS_PER_DAY,
    market_close: str = MARKET_CLOSE_1MIN,
):
    if existing_df.empty:
        return [(start_date, end_date)]

    first_dt = existing_df["Datetime"].min()
    last_dt = existing_df["Datetime"].max()
    first_date = first_dt.date()
    last_date = last_dt.date()
    market_open_time = datetime.strptime(MARKET_OPEN, "%H:%M").time()
    market_close_time = datetime.strptime(market_close, "%H:%M").time()

    ranges = []
    regular_rows = existing_df[
        (existing_df["Datetime"].dt.time >= market_open_time)
        & (existing_df["Datetime"].dt.time <= market_close_time)
    ].copy()
    if not regular_rows.empty:
        regular_counts = regular_rows.groupby(regular_rows["Datetime"].dt.date).size()
        partial_dates = regular_counts[
            (regular_counts.index >= start_date)
            & (regular_counts.index <= end_date)
            & (regular_counts < expected_bars_per_day)
        ].index
        ranges.extend((partial_date, partial_date) for partial_date in partial_dates)

    if first_date > start_date:
        older_end = (
            first_date if first_dt.time() > market_open_time else first_date - timedelta(days=1)
        )
        older_end = min(older_end, end_date)
        if start_date <= older_end:
            ranges.append((start_date, older_end))
    elif first_date == start_date and first_dt.time() > market_open_time:
        ranges.append((start_date, start_date))

    if last_dt.time() < market_close_time:
        newer_start = last_date
    else:
        newer_start = last_date + timedelta(days=1)

    if newer_start <= end_date:
        ranges.append((newer_start, end_date))

    merged_ranges = []
    for range_start, range_end in sorted(ranges):
        if not merged_ranges or range_start > merged_ranges[-1][1] + timedelta(days=1):
            merged_ranges.append([range_start, range_end])
        else:
            merged_ranges[-1][1] = max(merged_ranges[-1][1], range_end)

    return [(range_start, range_end) for range_start, range_end in merged_ranges]


def format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def count_history_chunks(range_start: date, range_end: date, chunk_days: int) -> int:
    chunk_days = min(HISTORY_INTRADAY_MAX_DAYS, max(1, int(chunk_days)))
    days = max(0, (range_end - range_start).days + 1)
    return (days + chunk_days - 1) // chunk_days


def fetch_candles(
    fyers,
    symbol: str,
    range_start: date,
    range_end: date,
    chunk_days: int,
    ist: ZoneInfo,
    download_stats: dict | None = None,
    log_fn=None,
    progress_callback=None,
) -> pd.DataFrame:
    all_candles = []
    chunk_end = range_end
    chunk_days = min(HISTORY_INTRADAY_MAX_DAYS, max(1, int(chunk_days)))
    log = log_fn or print

    while chunk_end >= range_start:
        chunk_start = max(range_start, chunk_end - timedelta(days=chunk_days - 1))
        params = {
            "symbol": resolve_fyers_symbol(symbol),
            "resolution": FYERS_BASE_RESOLUTION,
            "date_format": "1",
            "range_from": chunk_start.strftime("%Y-%m-%d"),
            "range_to": chunk_end.strftime("%Y-%m-%d"),
            "cont_flag": "1",
        }
        call_progressed = False
        try:
            if download_stats is not None:
                download_stats["history_calls"] += 1
            resp = fyers.history(data=params)
            if progress_callback is not None:
                progress_callback()
                call_progressed = True
            if not isinstance(resp, dict):
                log(f"Unexpected Fyers response for {symbol} {chunk_start} to {chunk_end}: {resp}")
                chunk_end = chunk_start - timedelta(days=1)
                continue

            if resp.get("s") == "error":
                log(f"Fyers error for {symbol} {chunk_start} to {chunk_end}: {resp}")
                code = resp.get("code")
                message = str(resp.get("message", "")).lower()
                if code == 429 or "request limit" in message or "rate limit" in message:
                    raise FyersRateLimitError(symbol, chunk_start, chunk_end, resp)
                chunk_end = chunk_start - timedelta(days=1)
                continue

            candles = resp.get("candles") or []
            if candles:
                all_candles.extend(candles)
        except Exception as e:
            if not call_progressed and progress_callback is not None:
                progress_callback()
            if isinstance(e, FyersRateLimitError):
                raise
            log(f"Error for {symbol} {chunk_start} to {chunk_end}: {e}")

        chunk_end = chunk_start - timedelta(days=1)

    return candles_to_dataframe(all_candles, ist)


def fallback_ema(close: pd.Series, window: int) -> pd.Series:
    return close.ewm(span=window, adjust=False, min_periods=window).mean()


def fallback_true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1)
    return ranges.max(axis=1)


def fallback_atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    tr = fallback_true_range(high, low, close)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def fallback_adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = fallback_atr(high, low, close, window)

    plus_di = 100 * plus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)
    return dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def add_indicators(df: pd.DataFrame, log_fn=None) -> pd.DataFrame:
    df = normalize_candles(df)
    if df.empty:
        return pd.DataFrame(columns=FINAL_COLUMNS)
    log = log_fn or print

    if ta is not None and len(df) >= MIN_TA_INDICATOR_ROWS:
        try:
            df["EMA9"] = ta.trend.ema_indicator(df["Close"], window=EMA_FAST_WINDOW)
            df["EMA21"] = ta.trend.ema_indicator(df["Close"], window=EMA_SLOW_WINDOW)

            adx = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"], window=ADX_WINDOW)
            df["ADX"] = adx.adx()

            df["ATR"] = ta.volatility.AverageTrueRange(
                high=df["High"], low=df["Low"], close=df["Close"], window=ATR_WINDOW
            ).average_true_range()
        except (TypeError, ValueError, IndexError) as e:
            log(f"ta indicator calculation failed; using pandas fallback indicators: {e}")
            df["EMA9"] = fallback_ema(df["Close"], EMA_FAST_WINDOW)
            df["EMA21"] = fallback_ema(df["Close"], EMA_SLOW_WINDOW)
            df["ADX"] = fallback_adx(df["High"], df["Low"], df["Close"], ADX_WINDOW)
            df["ATR"] = fallback_atr(df["High"], df["Low"], df["Close"], ATR_WINDOW)
    else:
        df["EMA9"] = fallback_ema(df["Close"], EMA_FAST_WINDOW)
        df["EMA21"] = fallback_ema(df["Close"], EMA_SLOW_WINDOW)
        df["ADX"] = fallback_adx(df["High"], df["Low"], df["Close"], ADX_WINDOW)
        df["ATR"] = fallback_atr(df["High"], df["Low"], df["Close"], ATR_WINDOW)

    for col in ["EMA9", "EMA21", "ADX", "ATR"]:
        df[col] = df[col].round(2)

    return df[FINAL_COLUMNS]


def aggregate_ohlcv(df: pd.DataFrame, group_cols) -> pd.DataFrame:
    grouped = df.groupby(group_cols, sort=True)
    result = grouped.agg(
        Datetime=("Datetime", "first"),
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
    ).reset_index(drop=True)
    return normalize_candles(result)


def resample_intraday(df_source: pd.DataFrame, minutes_per_bar: int) -> pd.DataFrame:
    df = normalize_candles(df_source)
    if df.empty:
        return df

    open_time = datetime.strptime(MARKET_OPEN, "%H:%M").time()
    close_time = datetime.strptime(MARKET_CLOSE_1MIN, "%H:%M").time()
    open_minutes = open_time.hour * 60 + open_time.minute
    df = df[(df["Datetime"].dt.time >= open_time) & (df["Datetime"].dt.time <= close_time)].copy()
    minutes = df["Datetime"].dt.hour * 60 + df["Datetime"].dt.minute
    df["_date"] = df["Datetime"].dt.date
    df["_bucket"] = ((minutes - open_minutes) // minutes_per_bar).astype(int)
    df = df[df["_bucket"] >= 0].copy()
    return aggregate_ohlcv(df, ["_date", "_bucket"])


def resample_to_5min(df_1min: pd.DataFrame) -> pd.DataFrame:
    return resample_intraday(df_1min, 5)


def resample_to_15min(df_1min: pd.DataFrame) -> pd.DataFrame:
    return resample_intraday(df_1min, 15)


def resample_to_daily(df_1min: pd.DataFrame) -> pd.DataFrame:
    df = normalize_candles(df_1min)
    if df.empty:
        return df

    df["_date"] = df["Datetime"].dt.date
    return aggregate_ohlcv(df, ["_date"])


def resample_to_weekly(df_1min: pd.DataFrame) -> pd.DataFrame:
    df = normalize_candles(df_1min)
    if df.empty:
        return df

    df["_week"] = df["Datetime"].dt.to_period("W-FRI")
    grouped = df.groupby("_week", sort=True)
    weekly = grouped.agg(
        Datetime=("Datetime", "last"),
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
    ).reset_index(drop=True)
    return normalize_candles(weekly)


def write_timeframe_files(
    symbol: str,
    output_folder: str,
    df_1min: pd.DataFrame,
    progress_callback=None,
    log_fn=None,
) -> dict:
    symbol_folder = symbol_data_folder(symbol, output_folder)
    os.makedirs(symbol_folder, exist_ok=True)
    mark_progress = progress_callback or (lambda: None)

    df_1min_raw = normalize_candles(df_1min)
    df_5min_raw = resample_to_5min(df_1min_raw)
    df_15min_raw = resample_to_15min(df_1min_raw)
    df_1d_raw = resample_to_daily(df_1min_raw)
    df_1w_raw = resample_to_weekly(df_1min_raw)

    df_1min_final = add_indicators(df_1min_raw, log_fn)
    df_5min_final = add_indicators(df_5min_raw, log_fn)
    df_15min_final = add_indicators(df_15min_raw, log_fn)
    df_1d_final = add_indicators(df_1d_raw, log_fn)
    df_1w_final = add_indicators(df_1w_raw, log_fn)

    paths = {
        TIMEFRAME_1MIN: timeframe_file_path(symbol, output_folder, TIMEFRAME_1MIN),
        TIMEFRAME_5MIN: timeframe_file_path(symbol, output_folder, TIMEFRAME_5MIN),
        TIMEFRAME_15MIN: timeframe_file_path(symbol, output_folder, TIMEFRAME_15MIN),
        TIMEFRAME_1D: timeframe_file_path(symbol, output_folder, TIMEFRAME_1D),
        TIMEFRAME_1W: timeframe_file_path(symbol, output_folder, TIMEFRAME_1W),
    }
    df_1min_final.to_csv(paths[TIMEFRAME_1MIN], index=False)
    mark_progress()
    df_5min_final.to_csv(paths[TIMEFRAME_5MIN], index=False)
    mark_progress()
    df_15min_final.to_csv(paths[TIMEFRAME_15MIN], index=False)
    mark_progress()
    df_1d_final.to_csv(paths[TIMEFRAME_1D], index=False)
    mark_progress()
    df_1w_final.to_csv(paths[TIMEFRAME_1W], index=False)
    mark_progress()
    return {
        "paths": paths,
        "rows": {
            TIMEFRAME_1MIN: len(df_1min_final),
            TIMEFRAME_5MIN: len(df_5min_final),
            TIMEFRAME_15MIN: len(df_15min_final),
            TIMEFRAME_1D: len(df_1d_final),
            TIMEFRAME_1W: len(df_1w_final),
        },
    }


def materialize_timeframe_files(symbol: str, output_folder: str = "./Data") -> dict:
    input_path = base_1min_input_path(symbol, output_folder)
    df_1min = read_existing_candles(input_path)
    if df_1min.empty:
        raise FileNotFoundError(f"No existing 1-minute data found for {symbol} at {input_path}")
    return write_timeframe_files(symbol, output_folder, df_1min)


def download_full_refresh_legacy(
    symbols: list[str], output_folder="./Data", chunk_days=60, total_days=365
):
    """
    Legacy full-refresh downloader kept for reference.

    Downloads OHLCV data for given symbols in chunk_days-day chunks over the past total_days days,
    writes raw data to CSV (with datetime formatting), and calculates EMA9, EMA21, ADX, and ATR21.
    """
    os.makedirs(output_folder, exist_ok=True)
    fyers = login()  # Fetch logged in FyersModel instance

    end_date = date.today()
    start_date = end_date - timedelta(days=total_days)

    utc = ZoneInfo("UTC")
    ist = ZoneInfo("Asia/Kolkata")

    for _symbol in tqdm(symbols, desc="Downloading and processing symbols"):
        symbol = str(_symbol)
        all_candles = []
        chunk_end = end_date

        while chunk_end > start_date:
            chunk_start = chunk_end - timedelta(days=chunk_days)
            if chunk_start < start_date:
                chunk_start = start_date

            params = {
                "symbol": resolve_fyers_symbol(symbol),
                "resolution": "5",
                "date_format": "1",
                "range_from": chunk_start.strftime("%Y-%m-%d"),
                "range_to": chunk_end.strftime("%Y-%m-%d"),
                "cont_flag": "1",
            }
            try:
                resp = fyers.history(data=params)
                candles = resp.get("candles") or []
                all_candles.extend(candles)
            except Exception as e:
                print(f"Error for {symbol} {chunk_start} to {chunk_end}: {e}")

            chunk_end = chunk_start - timedelta(days=1)

        if not all_candles:
            print(f"No data for {symbol}, skipping.")
            continue

        df = pd.DataFrame(all_candles, columns=["epoch", "Open", "High", "Low", "Close", "Volume"])
        df["Datetime"] = pd.to_datetime(df["epoch"], unit="s", utc=True)
        df["Datetime"] = df["Datetime"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
        df = df[["Datetime", "Open", "High", "Low", "Close", "Volume"]].sort_values("Datetime")

        # Save raw data
        file_path = os.path.join(output_folder, f"{symbol}.csv")
        df.to_csv(file_path, index=False)

        # Padding range for indicators
        first_ts = df["Datetime"].iloc[0]
        pad_start = (first_ts - timedelta(days=chunk_days)).strftime("%Y-%m-%d")
        pad_end = (first_ts - timedelta(seconds=1)).strftime("%Y-%m-%d")

        try:
            pad_resp = fyers.history(
                data={
                    "symbol": resolve_fyers_symbol(symbol),
                    "resolution": "5",
                    "date_format": "1",
                    "range_from": pad_start,
                    "range_to": pad_end,
                    "cont_flag": "1",
                }
            )
            pad_candles = pad_resp.get("candles") or []
        except Exception as e:
            print(f"Padding fetch error for {symbol}: {e}")
            pad_candles = []

        if pad_candles:
            df_pad = pd.DataFrame(
                pad_candles, columns=["epoch", "Open", "High", "Low", "Close", "Volume"]
            )
            df_pad["Datetime"] = (
                pd.to_datetime(df_pad["epoch"], unit="s", utc=True)
                .dt.tz_convert("Asia/Kolkata")
                .dt.tz_localize(None)
            )
            df_pad = df_pad[["Datetime", "Open", "High", "Low", "Close", "Volume"]]
            df_full = (
                pd.concat([df_pad, df], ignore_index=True)
                .drop_duplicates("Datetime")
                .sort_values("Datetime")
            )
        else:
            df_full = df.copy()

        # Indicators
        assert ta is not None, "ta library is required for legacy downloader"
        df_full["EMA9"] = ta.trend.ema_indicator(df_full["Close"], window=9)
        df_full["EMA21"] = ta.trend.ema_indicator(df_full["Close"], window=21)
        adx = ta.trend.ADXIndicator(df_full["High"], df_full["Low"], df_full["Close"], window=14)
        df_full["ADX"] = adx.adx()

        # Add ATR
        df_full["ATR"] = ta.volatility.AverageTrueRange(
            high=df_full["High"], low=df_full["Low"], close=df_full["Close"], window=21
        ).average_true_range()

        # Trim back to original data
        df_final = df_full[df_full["Datetime"] >= first_ts].reset_index(drop=True)

        # Round indicator columns to 2 decimals
        df_final["EMA9"] = df_final["EMA9"].round(2)
        df_final["EMA21"] = df_final["EMA21"].round(2)
        df_final["ADX"] = df_final["ADX"].round(2)
        df_final["ATR"] = df_final["ATR"].round(2)

        # Save final with indicators
        df_final.to_csv(file_path, index=False)

    print("✅ Download, indicator population (including ATR) complete.")


def download(
    symbols: list[str], output_folder="./Data", chunk_days=100, total_days=365, downloadStats=False
):
    """
    Incrementally downloads only missing OHLCV data for each symbol.

    Existing CSV data is preserved, missing older/newer ranges are fetched,
    rows are merged in Datetime order, duplicates are removed, and 5MIN,
    15MIN, 1D, and 1W files are derived locally from the 1MIN source.
    """
    started_at = time.perf_counter()
    stats = (
        {
            "history_calls": 0,
            "candles_fetched": 0,
            "symbols_processed": 0,
            "symbols_rate_limited": 0,
            "symbols_skipped_no_data": 0,
        }
        if downloadStats
        else None
    )
    os.makedirs(output_folder, exist_ok=True)

    ist = ZoneInfo("Asia/Kolkata")
    end_date = datetime.now(ist).date()
    start_date = end_date - timedelta(days=total_days)
    fyers = None

    planned_symbols = []
    total_work_units = 0
    for symbol in list(symbols):
        existing_df = read_existing_base_candles(symbol, output_folder)
        ranges_to_fetch = missing_date_ranges(existing_df, start_date, end_date)
        fetch_units = sum(
            count_history_chunks(range_start, range_end, chunk_days)
            for range_start, range_end in ranges_to_fetch
        )
        work_units = fetch_units + TIMEFRAME_WRITE_STEPS
        planned_symbols.append(
            {
                "symbol": symbol,
                "existing_df": existing_df,
                "ranges_to_fetch": ranges_to_fetch,
                "work_units": work_units,
            }
        )
        total_work_units += work_units

    progress = tqdm(
        total=total_work_units,
        desc="Downloading and processing",
        unit="step",
        dynamic_ncols=True,
    )
    download_messages = []
    try:
        for plan in planned_symbols:
            symbol = plan["symbol"]
            existing_df = plan["existing_df"]
            ranges_to_fetch = plan["ranges_to_fetch"]
            symbol_done_units = 0

            def advance_progress(units: int = 1):
                nonlocal symbol_done_units
                if units <= 0:
                    return
                progress.update(units)
                symbol_done_units += units

            def finish_symbol_progress():
                remaining_units = plan["work_units"] - symbol_done_units
                if remaining_units > 0:
                    advance_progress(remaining_units)

            log = download_messages.append

            fetched_parts = []
            rate_limited = False
            if ranges_to_fetch and fyers is None:
                fyers = login()

            for range_start, range_end in ranges_to_fetch:
                try:
                    fetched = fetch_candles(
                        fyers,
                        symbol,
                        range_start,
                        range_end,
                        chunk_days,
                        ist,
                        stats,
                        log,
                        advance_progress,
                    )
                except FyersRateLimitError as e:
                    rate_limited = True
                    if stats is not None:
                        stats["symbols_rate_limited"] += 1
                    log(
                        f"{symbol}: stopped download because Fyers rate limit was reached "
                        f"for {e.range_start} to {e.range_end}. Try again after the API limit resets."
                    )
                    break
                if not fetched.empty:
                    fetched_parts.append(fetched)
                    if stats is not None:
                        stats["candles_fetched"] += len(fetched)

            if rate_limited:
                log(f"{symbol}: preserving existing CSV files; no partial refresh was written.")
                finish_symbol_progress()
                continue

            if existing_df.empty and not fetched_parts:
                log(f"No data for {symbol}, skipping.")
                if stats is not None:
                    stats["symbols_skipped_no_data"] += 1
                finish_symbol_progress()
                continue

            df_parts = [existing_df] + fetched_parts
            df_merged = normalize_candles(pd.concat(df_parts, ignore_index=True))
            output = write_timeframe_files(symbol, output_folder, df_merged, advance_progress, log)
            if stats is not None:
                stats["symbols_processed"] += 1

            if ranges_to_fetch:
                fetched_rows = sum(len(part) for part in fetched_parts)
                log(
                    f"{symbol}: fetched {fetched_rows} missing rows, "
                    f"saved {output['rows'][TIMEFRAME_1MIN]} 1MIN rows, "
                    f"{output['rows'][TIMEFRAME_5MIN]} 5MIN rows, "
                    f"{output['rows'][TIMEFRAME_15MIN]} 15MIN rows, "
                    f"{output['rows'][TIMEFRAME_1D]} 1D rows, "
                    f"{output['rows'][TIMEFRAME_1W]} 1W rows."
                )
            else:
                log(
                    f"{symbol}: local CSV already covers requested range; "
                    f"refreshed {output['rows'][TIMEFRAME_1MIN]} 1MIN rows, "
                    f"{output['rows'][TIMEFRAME_5MIN]} 5MIN rows, "
                    f"{output['rows'][TIMEFRAME_15MIN]} 15MIN rows, "
                    f"{output['rows'][TIMEFRAME_1D]} 1D rows, "
                    f"{output['rows'][TIMEFRAME_1W]} 1W rows."
                )
            finish_symbol_progress()
    finally:
        if hasattr(progress, "close"):
            progress.close()

    for message in download_messages:
        print(message)

    if stats is not None:
        elapsed = time.perf_counter() - started_at
        print(
            f"API calls: {stats['history_calls']}, "
            f"Downloaded Candles: {stats['candles_fetched']}, "
            f"Time: {format_elapsed(elapsed)}"
        )


def Login():
    return login()


def FetchSymbols(key=None):
    return fetchSymbols(key)


def ResolveFyersSymbol(symbol: str) -> str:
    return resolve_fyers_symbol(symbol)


def IsMarketOpen(fyers):
    return isMarketOpen(fyers)


def CheckLastCandle(symbol: str, path: str = "Data") -> datetime:
    return checkLastCandle(symbol, path)


def UpdateCsv(symbol: str, fyers, path: str = "Data") -> bool:
    return UpdateCSV(symbol, fyers, path)


def NormalizeCandles(df: pd.DataFrame) -> pd.DataFrame:
    return normalize_candles(df)


def ReadExistingCandles(file_path: str) -> pd.DataFrame:
    return read_existing_candles(file_path)


def CandlesToDataFrame(candles, ist: ZoneInfo) -> pd.DataFrame:
    return candles_to_dataframe(candles, ist)


def AddIndicators(df: pd.DataFrame, log_fn=None) -> pd.DataFrame:
    return add_indicators(df, log_fn)


def WriteTimeframeFiles(
    symbol: str, output_folder: str, df_1min: pd.DataFrame, progress_callback=None, log_fn=None
) -> dict:
    return write_timeframe_files(symbol, output_folder, df_1min, progress_callback, log_fn)


def MaterializeTimeframeFiles(symbol: str, output_folder: str = "./Data") -> dict:
    return materialize_timeframe_files(symbol, output_folder)


def Download(symbols, output_folder="./Data", chunk_days=100, total_days=365, downloadStats=False):
    return download(symbols, output_folder, chunk_days, total_days, downloadStats)


if __name__ == "__main__":
    Download(
        ["CGPOWER"], output_folder="./Data", chunk_days=100, total_days=100, downloadStats=True
    )
