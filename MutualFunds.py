from __future__ import annotations

import csv
import json
import os
import time
from datetime import date
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from Config.MutualFunds import GetMutualFundDefinition, MutualFundDefinition


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_FOLDER = ROOT / "Data"
DEFAULT_FUND = "PPFCF_DIRECT_GROWTH"
AMFI_LATEST_NAV_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
AMFI_HISTORY_NAV_URL = "https://portal.amfiindia.com/NavHistoryReport_Rpt_Po.aspx"
NAV_COLUMNS = ["Date", "NAV", "DailyReturnPct", "Source"]
NAV_MATCH_TOLERANCE = 0.0001
MAX_PROVIDER_ONLY_VERIFICATIONS = 10


class MutualFundDataError(RuntimeError):
    pass


class _HtmlTableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.Rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data):
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            self._row.append(" ".join("".join(self._cell_parts).split()))
            self._cell_parts = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.Rows.append(self._row)
            self._row = None
            self._cell_parts = None


def FetchUrlText(
    url: str,
    *,
    timeout: int = 30,
    retries: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    last_error: Exception | None = None
    request = Request(url, headers={"User-Agent": "FyersResearch/1.0"})

    for attempt in range(max(1, int(retries))):
        try:
            with urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise MutualFundDataError(f"Unexpected HTTP status {status} from {url}")
                return response.read().decode("utf-8-sig")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < max(1, int(retries)):
                sleep_fn(2**attempt)

    raise MutualFundDataError(
        f"Unable to fetch mutual-fund data from {url} after {max(1, int(retries))} attempts: {last_error}"
    ) from last_error


def ParseHistoricalNav(payload_text: str, fund: MutualFundDefinition) -> pd.DataFrame:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise MutualFundDataError("MFAPI returned invalid JSON") from exc

    if payload.get("status") != "SUCCESS":
        raise MutualFundDataError(f"MFAPI returned unsuccessful status: {payload.get('status')!r}")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise MutualFundDataError("MFAPI response is missing fund metadata")

    try:
        scheme_code_str = meta.get("scheme_code")
        if scheme_code_str is None:
            raise MutualFundDataError("MFAPI metadata contains an invalid scheme code")
        response_code = int(scheme_code_str)
    except (TypeError, ValueError) as exc:
        raise MutualFundDataError("MFAPI metadata contains an invalid scheme code") from exc

    if response_code != fund.SchemeCode:
        raise MutualFundDataError(
            f"MFAPI scheme mismatch: expected {fund.SchemeCode}, received {response_code}"
        )
    if str(meta.get("isin_growth") or "").strip().upper() != fund.IsinGrowth:
        raise MutualFundDataError(
            f"MFAPI ISIN mismatch for scheme {fund.SchemeCode}: expected {fund.IsinGrowth}"
        )
    if str(meta.get("scheme_name") or "").strip() != fund.SchemeName:
        raise MutualFundDataError(
            f"MFAPI name mismatch for scheme {fund.SchemeCode}: {meta.get('scheme_name')!r}"
        )

    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise MutualFundDataError(f"MFAPI returned no NAV history for scheme {fund.SchemeCode}")

    frame = pd.DataFrame(rows)
    if not {"date", "nav"}.issubset(frame.columns):
        raise MutualFundDataError("MFAPI NAV history is missing date or nav fields")

    parsed_dates = pd.to_datetime(frame["date"], format="%d-%m-%Y", errors="coerce")
    parsed_nav = pd.to_numeric(frame["nav"], errors="coerce")
    invalid = parsed_dates.isna() | parsed_nav.isna() | (parsed_nav <= 0)
    if invalid.any():
        raise MutualFundDataError(f"MFAPI returned {int(invalid.sum())} malformed NAV rows")

    result = pd.DataFrame(
        {
            "Date": parsed_dates.dt.normalize(),
            "NAV": parsed_nav.astype(float),
            "Source": "MFAPI",
        }
    )
    return ValidateNavFrame(result, "MFAPI history")


def ParseLatestAmfiNav(payload_text: str, fund: MutualFundDefinition) -> pd.DataFrame:
    reader = csv.reader(StringIO(payload_text), delimiter=";")
    matches = [row for row in reader if row and row[0].strip() == str(fund.SchemeCode)]
    if len(matches) != 1:
        raise MutualFundDataError(
            f"AMFI latest NAV file contains {len(matches)} rows for scheme {fund.SchemeCode}; expected 1"
        )

    row = matches[0]
    if len(row) < 8:
        raise MutualFundDataError(f"AMFI row for scheme {fund.SchemeCode} is incomplete")
    if row[1].strip().upper() != fund.IsinGrowth:
        raise MutualFundDataError(
            f"AMFI ISIN mismatch for scheme {fund.SchemeCode}: expected {fund.IsinGrowth}"
        )
    if row[3].strip() != fund.AmfiSchemeName:
        raise MutualFundDataError(f"AMFI scheme name mismatch for scheme {fund.SchemeCode}")
    if row[4].strip().lower() != fund.Plan.lower() or row[5].strip().lower() != fund.Option.lower():
        raise MutualFundDataError(f"AMFI plan/option mismatch for scheme {fund.SchemeCode}")

    date = pd.to_datetime(row[7].strip(), format="%d-%b-%Y", errors="coerce")
    nav = pd.to_numeric(row[6].strip(), errors="coerce")
    if pd.isna(date) or pd.isna(nav) or float(nav) <= 0:
        raise MutualFundDataError(f"AMFI returned an invalid latest NAV for scheme {fund.SchemeCode}")

    return pd.DataFrame(
        [{"Date": date.normalize(), "NAV": float(nav), "Source": "AMFI"}]
    )


def ParseOfficialHistory(payload_text: str, fund: MutualFundDefinition) -> pd.DataFrame:
    parser = _HtmlTableRows()
    parser.feed(payload_text)

    records = []
    for cells in parser.Rows:
        if len(cells) < 3:
            continue
        parsed_date = pd.to_datetime(cells[0], format="%d-%m-%Y", errors="coerce")
        parsed_nav = pd.to_numeric(cells[1], errors="coerce")
        if pd.isna(parsed_date) or pd.isna(parsed_nav):
            continue
        records.append(
            {"Date": parsed_date.normalize(), "NAV": float(parsed_nav), "Source": "PPFAS"}
        )

    if not records:
        raise MutualFundDataError(
            f"Official history returned no Direct Plan NAV rows for scheme {fund.SchemeCode}"
        )
    result = ValidateNavFrame(pd.DataFrame(records), "official PPFAS history")
    if result["Date"].min().date() != fund.InceptionDate:
        raise MutualFundDataError(
            f"Official history starts on {result['Date'].min().date()}, expected {fund.InceptionDate}"
        )
    return result


def ParseAmfiHistoricalNav(
    payload_text: str,
    fund: MutualFundDefinition,
    expected_date: date,
) -> pd.DataFrame:
    parser = _HtmlTableRows()
    parser.feed(payload_text)
    scheme_rows = [i for i, cells in enumerate(parser.Rows) if fund.SchemeName in cells]
    if len(scheme_rows) != 1:
        raise MutualFundDataError(
            f"AMFI history contains {len(scheme_rows)} rows for {fund.SchemeName} on {expected_date}"
        )

    index = scheme_rows[0]
    if index + 1 >= len(parser.Rows) or not parser.Rows[index + 1]:
        raise MutualFundDataError(f"AMFI history is missing NAV details for {expected_date}")
    nav = pd.to_numeric(parser.Rows[index + 1][0], errors="coerce")
    if pd.isna(nav) or float(nav) <= 0:
        raise MutualFundDataError(f"AMFI history returned an invalid NAV for {expected_date}")
    return pd.DataFrame(
        [{"Date": pd.Timestamp(expected_date), "NAV": float(nav), "Source": "AMFI_HISTORY"}]
    )


def ValidateNavFrame(frame: pd.DataFrame, label: str = "NAV data") -> pd.DataFrame:
    required = {"Date", "NAV"}
    if not required.issubset(frame.columns):
        raise MutualFundDataError(f"{label} is missing required columns: {sorted(required - set(frame.columns))}")

    result = frame.copy()
    result["Date"] = pd.to_datetime(result["Date"], errors="coerce").dt.normalize()
    result["NAV"] = pd.to_numeric(result["NAV"], errors="coerce")
    if "Source" not in result.columns:
        result["Source"] = "LOCAL"

    invalid = result["Date"].isna() | result["NAV"].isna() | (result["NAV"] <= 0)
    if invalid.any():
        raise MutualFundDataError(f"{label} contains {int(invalid.sum())} invalid rows")

    conflicts = result.groupby("Date")["NAV"].agg(lambda values: values.max() - values.min())
    conflicts = conflicts[conflicts > NAV_MATCH_TOLERANCE]
    if not conflicts.empty:
        sample = conflicts.index[0].date().isoformat()
        raise MutualFundDataError(f"{label} contains conflicting NAV values on {sample}")

    source_priority = result["Source"].map(
        {
            "LOCAL": 0,
            "MFAPI": 1,
            "MFAPI_PPFAS": 2,
            "PPFAS": 3,
            "PPFAS_CORRECTED": 4,
            "AMFI_HISTORY": 5,
            "AMFI": 6,
        }
    ).fillna(0)
    result = result.assign(_SourcePriority=source_priority)
    result = result.sort_values(["Date", "_SourcePriority"])
    result = result.drop_duplicates(subset=["Date"], keep="last")
    result = result.drop(columns=["_SourcePriority"])
    result = result.sort_values("Date").reset_index(drop=True)
    return result


def MutualFundFilePath(
    fund_name: str = DEFAULT_FUND,
    *,
    output_folder: str | Path = DEFAULT_DATA_FOLDER,
) -> Path:
    fund = GetMutualFundDefinition(fund_name)
    return Path(output_folder) / "MutualFunds" / fund.Key / f"{fund.Key}_1D.csv"


def ReadExistingNav(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["Date", "NAV", "Source"])
    frame = pd.read_csv(path)
    return ValidateNavFrame(frame, f"existing NAV file {path}")


def _FormatAmfiDate(value: date) -> str:
    month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{value.day:02d}-{month[value.month - 1]}-{value.year:04d}"


def VerifyProviderOnlyRows(
    provider_only: pd.DataFrame,
    existing: pd.DataFrame,
    fund: MutualFundDefinition,
    *,
    timeout: int,
    retries: int,
) -> pd.DataFrame:
    if provider_only.empty:
        return pd.DataFrame(columns=["Date", "NAV", "Source"])
    if len(provider_only) > MAX_PROVIDER_ONLY_VERIFICATIONS:
        raise MutualFundDataError(
            f"MFAPI has {len(provider_only)} dates missing from PPFAS; refusing excessive AMFI checks"
        )

    verified = []
    existing_verified = existing[existing["Source"].isin(["AMFI_HISTORY", "AMFI"])]
    for row in provider_only.itertuples(index=False):
        cached = existing_verified[existing_verified["Date"] == row.Date]
        if not cached.empty and abs(float(cached.iloc[-1]["NAV"]) - float(row.NAV)) <= NAV_MATCH_TOLERANCE:
            verified.append(
                {"Date": row.Date, "NAV": float(row.NAV), "Source": "AMFI_HISTORY"}
            )
            continue

        query = urlencode({"frmdate": _FormatAmfiDate(row.Date.date()), "rpt": "0"})
        payload = FetchUrlText(
            f"{AMFI_HISTORY_NAV_URL}?{query}",
            timeout=timeout,
            retries=retries,
        )
        amfi_row = ParseAmfiHistoricalNav(payload, fund, row.Date.date()).iloc[0]
        if abs(float(amfi_row["NAV"]) - float(row.NAV)) > NAV_MATCH_TOLERANCE:
            raise MutualFundDataError(
                f"MFAPI provider-only NAV disagrees with AMFI on {row.Date.date()}: "
                f"{row.NAV} vs {amfi_row['NAV']}"
            )
        verified.append(amfi_row.to_dict())
    return ValidateNavFrame(pd.DataFrame(verified), "AMFI-verified provider-only NAV rows")


def MergeNavData(
    history: pd.DataFrame,
    official_history: pd.DataFrame,
    latest: pd.DataFrame,
    verified_provider_only: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    history = ValidateNavFrame(history, "MFAPI history")
    official_history = ValidateNavFrame(official_history, "official PPFAS history")
    latest = ValidateNavFrame(latest, "AMFI latest NAV")
    verified_provider_only = ValidateNavFrame(
        verified_provider_only,
        "AMFI-verified provider-only NAV rows",
    )

    comparison = history.merge(
        official_history[["Date", "NAV"]],
        on="Date",
        how="outer",
        suffixes=("_Mfapi", "_Ppfas"),
        indicator=True,
    )
    overlap = comparison[comparison["_merge"] == "both"].copy()
    overlap["Difference"] = (overlap["NAV_Mfapi"] - overlap["NAV_Ppfas"]).abs()
    corrected_dates = set(overlap.loc[overlap["Difference"] > NAV_MATCH_TOLERANCE, "Date"])
    matched_dates = set(overlap.loc[overlap["Difference"] <= NAV_MATCH_TOLERANCE, "Date"])
    provider_only_dates = set(comparison.loc[comparison["_merge"] == "left_only", "Date"])
    official_only_dates = set(comparison.loc[comparison["_merge"] == "right_only", "Date"])

    if set(verified_provider_only["Date"]) != provider_only_dates:
        raise MutualFundDataError("Not all MFAPI provider-only NAV rows were independently verified")

    official_history = official_history.copy()
    official_history.loc[official_history["Date"].isin(matched_dates), "Source"] = "MFAPI_PPFAS"
    official_history.loc[official_history["Date"].isin(corrected_dates), "Source"] = "PPFAS_CORRECTED"

    latest_overlap = official_history.merge(latest, on="Date", suffixes=("_Ppfas", "_Amfi"))
    if not latest_overlap.empty:
        differences = (latest_overlap["NAV_Ppfas"] - latest_overlap["NAV_Amfi"]).abs()
        if (differences > NAV_MATCH_TOLERANCE).any():
            row = latest_overlap.loc[differences.idxmax()]
            raise MutualFundDataError(
                "Latest PPFAS and AMFI NAV values disagree on "
                f"{row['Date'].date().isoformat()}: {row['NAV_Ppfas']} vs {row['NAV_Amfi']}"
            )

    combined = ValidateNavFrame(
        pd.concat([official_history, verified_provider_only, latest], ignore_index=True),
        "combined NAV data",
    )
    combined["DailyReturnPct"] = combined["NAV"].pct_change(fill_method=None).mul(100).round(6)
    quality = {
        "matched_rows": len(matched_dates),
        "corrected_rows": len(corrected_dates),
        "missing_from_mfapi_rows": len(official_only_dates),
        "amfi_verified_provider_only_rows": len(provider_only_dates),
    }
    return combined[NAV_COLUMNS], quality


def WriteNavAtomically(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            suffix=".tmp",
            prefix=f"{path.stem}_",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            frame.to_csv(handle, index=False, date_format="%Y-%m-%d")
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def DownloadMutualFund(
    fund_name: str = DEFAULT_FUND,
    *,
    output_folder: str | Path = DEFAULT_DATA_FOLDER,
    timeout: int = 30,
    retries: int = 3,
    log_fn: Callable[[str], None] | None = print,
) -> dict:
    fund = GetMutualFundDefinition(fund_name)
    path = MutualFundFilePath(fund.Key, output_folder=output_folder)
    existing = ReadExistingNav(path)

    history_text = FetchUrlText(fund.HistoryUrl, timeout=timeout, retries=retries)
    history = ParseHistoricalNav(history_text, fund)

    official_query = urlencode(
        {"dt1": fund.InceptionDate.isoformat(), "dt2": date.today().isoformat()}
    )
    official_text = FetchUrlText(
        f"{fund.OfficialHistoryUrl}?{official_query}",
        timeout=timeout,
        retries=retries,
    )
    official_history = ParseOfficialHistory(official_text, fund)

    amfi_text = FetchUrlText(AMFI_LATEST_NAV_URL, timeout=timeout, retries=retries)
    latest = ParseLatestAmfiNav(amfi_text, fund)

    provider_only = history[~history["Date"].isin(official_history["Date"])]
    verified_provider_only = VerifyProviderOnlyRows(
        provider_only,
        existing,
        fund,
        timeout=timeout,
        retries=retries,
    )
    final, quality = MergeNavData(
        history,
        official_history,
        latest,
        verified_provider_only,
    )
    WriteNavAtomically(final, path)

    history_latest = history["Date"].max().date()
    official_latest = latest["Date"].max().date()
    result = {
        "fund": fund.Key,
        "scheme_code": fund.SchemeCode,
        "path": path,
        "rows": len(final),
        "start_date": final["Date"].min().date(),
        "end_date": final["Date"].max().date(),
        "mfapi_latest": history_latest,
        "amfi_latest": official_latest,
        **quality,
    }
    if log_fn is not None:
        log_fn(
            f"{fund.Key}: saved {len(final)} daily NAV rows "
            f"({result['start_date']} to {result['end_date']}); "
            f"MFAPI latest={history_latest}, AMFI latest={official_latest}; "
            f"corrected={quality['corrected_rows']}, "
            f"MFAPI missing={quality['missing_from_mfapi_rows']}, "
            f"AMFI-verified extras={quality['amfi_verified_provider_only_rows']}."
        )
    return result
