from Actions import ClearScreen, RunExample

if __name__ == "__main__":
    ClearScreen()

    # Main command panel. Change these values and run Main.py.
    ACTION = "download"
    SYMBOLS = ["TMPV"]
    STRATEGY_NAME = "G01"

    # Historical scan/backtest params.
    DAYS = 5
    UPDATE_DATA = None
    REFRESH_DAYS = 120

    # Download params.
    DOWNLOAD_TOTAL_DAYS = 400
    CHUNK_DAYS = 100
    DOWNLOAD_STATS = True

    # Mutual-fund params.
    MUTUAL_FUND_NAME = "PPFCF_DIRECT_GROWTH"
    MUTUAL_FUND_TIMEOUT = 30
    MUTUAL_FUND_RETRIES = 3

    # Paper trade params.
    PAPER_POLL_SECONDS = 30
    PAPER_DURATION_MINUTES = 240
    PAPER_INITIAL_BALANCE = 1000.0
    PAPER_LEVERAGE = 5.0
    PAPER_RESET = False
    PAPER_MANAGE_LIVE_TICK = True

    # Actions:
    # "download"     Refresh Data/{SYMBOL} from FYERS.
    # "mutual_fund"  Refresh daily mutual-fund NAV history without FYERS login.
    # "materialize"  Rebuild 5MIN/15MIN/1D/1W from existing 1MIN CSV.
    # "scan"         Refresh data, then scan the last DAYS trading days.
    # "scan_local"   Scan the last DAYS trading days without API calls.
    # "backtest"     Full local backtest.
    # "paper"        Live/off-market paper trader orchestration.

    RunExample(
        ACTION,
        SYMBOLS,
        strategyName=STRATEGY_NAME,
        days=DAYS,
        updateData=UPDATE_DATA,
        refreshDays=REFRESH_DAYS,
        downloadTotalDays=DOWNLOAD_TOTAL_DAYS,
        chunkDays=CHUNK_DAYS,
        downloadStats=DOWNLOAD_STATS,
        paperPollSeconds=PAPER_POLL_SECONDS,
        paperDurationMinutes=PAPER_DURATION_MINUTES,
        paperInitialBalance=PAPER_INITIAL_BALANCE,
        paperLeverage=PAPER_LEVERAGE,
        paperReset=PAPER_RESET,
        paperManageLiveTick=PAPER_MANAGE_LIVE_TICK,
        mutualFundName=MUTUAL_FUND_NAME,
        mutualFundTimeout=MUTUAL_FUND_TIMEOUT,
        mutualFundRetries=MUTUAL_FUND_RETRIES,
    )
