from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MutualFundDefinition:
    Key: str
    SchemeCode: int
    SchemeName: str
    IsinGrowth: str
    AmfiSchemeName: str
    Plan: str
    Option: str
    InceptionDate: date
    OfficialHistoryUrl: str

    @property
    def HistoryUrl(self) -> str:
        return f"https://api.mfapi.in/mf/{self.SchemeCode}"


PARAG_PARIKH_FLEXI_CAP_DIRECT_GROWTH = MutualFundDefinition(
    Key="PPFCF_DIRECT_GROWTH",
    SchemeCode=122639,
    SchemeName="Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
    IsinGrowth="INF879O01027",
    AmfiSchemeName="Parag Parikh Flexi Cap Fund",
    Plan="Direct Plan",
    Option="Growth",
    InceptionDate=date(2013, 5, 28),
    OfficialHistoryUrl="https://amc.ppfas.com/schemes/nav-history/data.php",
)


_FUND_ALIASES = {
    "122639": PARAG_PARIKH_FLEXI_CAP_DIRECT_GROWTH,
    "PARAG_PARIKH_FLEXI_CAP_DIRECT_GROWTH": PARAG_PARIKH_FLEXI_CAP_DIRECT_GROWTH,
    "PPFCF": PARAG_PARIKH_FLEXI_CAP_DIRECT_GROWTH,
    "PPFCF_DIRECT_GROWTH": PARAG_PARIKH_FLEXI_CAP_DIRECT_GROWTH,
}


def GetMutualFundDefinition(name: str) -> MutualFundDefinition:
    key = str(name).strip().upper().replace(" ", "_")
    try:
        return _FUND_ALIASES[key]
    except KeyError as exc:
        available = ", ".join(sorted({fund.Key for fund in _FUND_ALIASES.values()}))
        raise ValueError(f"Unknown mutual fund {name!r}. Available funds: {available}") from exc
