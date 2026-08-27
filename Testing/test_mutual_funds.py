from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import Actions as Main
import MutualFunds
from Config.MutualFunds import PARAG_PARIKH_FLEXI_CAP_DIRECT_GROWTH


FUND = PARAG_PARIKH_FLEXI_CAP_DIRECT_GROWTH


def HistoricalPayload(rows=None, **meta_overrides):
    meta = {
        "fund_house": "PPFAS Mutual Fund",
        "scheme_type": "Open Ended Schemes",
        "scheme_category": "Equity Scheme - Flexi Cap Fund",
        "scheme_code": FUND.SchemeCode,
        "scheme_name": FUND.SchemeName,
        "isin_growth": FUND.IsinGrowth,
        "isin_div_reinvestment": None,
    }
    meta.update(meta_overrides)
    return json.dumps(
        {
            "meta": meta,
            "data": rows
            or [
                {"date": "23-08-2026", "nav": "90.50000"},
                {"date": "22-08-2026", "nav": "90.00000"},
            ],
            "status": "SUCCESS",
        }
    )


def AmfiPayload(date="24-Aug-2026", nav="90.9964"):
    return "\n".join(
        [
            "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date",
            "PPFAS Mutual Fund",
            f"122639;INF879O01027;-;Parag Parikh Flexi Cap Fund;Direct Plan;Growth;{nav};{date}",
        ]
    )


def OfficialHistoryPayload(rows=None):
    rows = rows or [
        ("24-08-2026", "90.9964", "82.9245"),
        ("23-08-2026", "90.5000", "82.5000"),
        ("22-08-2026", "90.0000", "82.0000"),
        ("21-08-2026", "89.5000", "81.5000"),
        ("28-05-2013", "9.9992", "9.9991"),
    ]
    body = "".join(
        f'<tr><td colspan="2">{date}</td><td>{direct}</td><td>{regular}</td></tr>'
        for date, direct, regular in rows
    )
    return f"<html><table>{body}</table></html>"


def AmfiHistoricalPayload(nav="26.9211"):
    return (
        "<html><table>"
        f"<tr><td colspan='4'>{FUND.SchemeName}</td></tr>"
        f"<tr><td>{nav}</td><td></td><td></td><td>22-Oct-2019 21:33:48</td></tr>"
        "</table></html>"
    )


class MutualFundTests(unittest.TestCase):
    def test_historical_parser_validates_identity_and_sorts_dates(self):
        frame = MutualFunds.ParseHistoricalNav(HistoricalPayload(), FUND)

        self.assertEqual(frame["Date"].dt.strftime("%Y-%m-%d").tolist(), ["2026-08-22", "2026-08-23"])
        self.assertEqual(frame["Source"].unique().tolist(), ["MFAPI"])

        with self.assertRaises(MutualFunds.MutualFundDataError):
            MutualFunds.ParseHistoricalNav(HistoricalPayload(scheme_code=999999), FUND)

    def test_download_merges_existing_history_and_official_latest(self):
        def FakeFetch(url, **_kwargs):
            if "mfapi.in" in url:
                return HistoricalPayload()
            if "amc.ppfas.com" in url:
                return OfficialHistoryPayload()
            return AmfiPayload()

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            path = MutualFunds.MutualFundFilePath(output_folder=tmp)
            path.parent.mkdir(parents=True)
            pd.DataFrame(
                [{"Date": "2026-08-21", "NAV": 89.5, "DailyReturnPct": None, "Source": "AMFI"}]
            ).to_csv(path, index=False)

            with patch.object(MutualFunds, "FetchUrlText", side_effect=FakeFetch):
                result = MutualFunds.DownloadMutualFund(output_folder=tmp, log_fn=None)

            saved = pd.read_csv(path, parse_dates=["Date"])
            self.assertEqual(result["rows"], 5)
            self.assertEqual(saved["Date"].dt.strftime("%Y-%m-%d").tolist()[-1], "2026-08-24")
            self.assertEqual(float(saved.iloc[-1]["NAV"]), 90.9964)
            self.assertEqual(saved.iloc[-1]["Source"], "AMFI")
            aug_22 = saved[saved["Date"] == pd.Timestamp("2026-08-22")].iloc[0]
            self.assertAlmostEqual(float(aug_22["DailyReturnPct"]), 0.558659, places=6)

    def test_disagreement_stops_before_overwriting_existing_file(self):
        history = HistoricalPayload(rows=[{"date": "24-08-2026", "nav": "90.00000"}])

        def FakeFetch(url, **_kwargs):
            if "mfapi.in" in url:
                return history
            if "amc.ppfas.com" in url:
                return OfficialHistoryPayload(
                    rows=[
                        ("24-08-2026", "90.0000", "82.0000"),
                        ("28-05-2013", "9.9992", "9.9991"),
                    ]
                )
            return AmfiPayload(nav="91.0000")

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            path = MutualFunds.MutualFundFilePath(output_folder=tmp)
            path.parent.mkdir(parents=True)
            original = "Date,NAV,DailyReturnPct,Source\n2026-08-23,89.5,,AMFI\n"
            path.write_text(original, encoding="utf-8")

            with patch.object(MutualFunds, "FetchUrlText", side_effect=FakeFetch):
                with self.assertRaisesRegex(MutualFunds.MutualFundDataError, "disagree"):
                    MutualFunds.DownloadMutualFund(output_folder=tmp, log_fn=None)

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_official_history_repairs_provider_errors_and_verifies_extra_dates(self):
        history = HistoricalPayload(
            rows=[
                {"date": "22-10-2019", "nav": "26.9211"},
                {"date": "26-12-2024", "nav": "87.6152"},
                {"date": "24-08-2026", "nav": "90.9964"},
                {"date": "28-05-2013", "nav": "9.9992"},
            ]
        )
        official = OfficialHistoryPayload(
            rows=[
                ("20-12-2023", "68.9027", "63.9277"),
                ("26-12-2024", "87.5536", "80.6413"),
                ("24-08-2026", "90.9964", "82.9245"),
                ("28-05-2013", "9.9992", "9.9991"),
            ]
        )

        def FakeFetch(url, **_kwargs):
            if "mfapi.in" in url:
                return history
            if "amc.ppfas.com" in url:
                return official
            if "NavHistoryReport" in url:
                return AmfiHistoricalPayload()
            return AmfiPayload()

        with TemporaryDirectory(dir=str(Path.cwd())) as tmp:
            with patch.object(MutualFunds, "FetchUrlText", side_effect=FakeFetch):
                result = MutualFunds.DownloadMutualFund(output_folder=tmp, log_fn=None)

            saved = pd.read_csv(result["path"], parse_dates=["Date"])
            corrected = saved[saved["Date"] == pd.Timestamp("2024-12-26")].iloc[0]
            verified = saved[saved["Date"] == pd.Timestamp("2019-10-22")].iloc[0]
            self.assertEqual(float(corrected["NAV"]), 87.5536)
            self.assertEqual(corrected["Source"], "PPFAS_CORRECTED")
            self.assertEqual(verified["Source"], "AMFI_HISTORY")
            self.assertEqual(result["corrected_rows"], 1)
            self.assertEqual(result["missing_from_mfapi_rows"], 1)
            self.assertEqual(result["amfi_verified_provider_only_rows"], 1)

    def test_main_example_routes_mutual_fund_action_without_fyers_login(self):
        expected = {"rows": 123}
        with patch.object(Main, "DownloadMutualFund", return_value=expected) as download:
            result = Main.RunExample(
                "mutual_fund",
                "IGNORED",
                mutualFundName="PPFCF",
                outputFolder="somewhere",
            )

        self.assertEqual(result, expected)
        download.assert_called_once_with(
            "PPFCF",
            output_folder="somewhere",
            timeout=30,
            retries=3,
        )


if __name__ == "__main__":
    unittest.main()
