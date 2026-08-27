from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALENDAR_PATH = ROOT / "Config" / "MarketHolidays" / "NSE_CM_2026.json"


def ParseClock(value: str):
    return datetime.strptime(value, "%H:%M").time()


@lru_cache(maxsize=8)
def LoadMarketCalendar(path: str | Path = DEFAULT_CALENDAR_PATH) -> dict[str, Any]:
    calendar_path = Path(path)
    if not calendar_path.exists():
        raise FileNotFoundError(f"Market calendar not found: {calendar_path}")
    return json.loads(calendar_path.read_text(encoding="utf-8"))


def SessionOpen(calendar: dict[str, Any] | None = None):
    cfg = calendar or LoadMarketCalendar()
    return ParseClock(cfg.get("regular_session", {}).get("open", "09:15"))


def SessionClose(calendar: dict[str, Any] | None = None):
    cfg = calendar or LoadMarketCalendar()
    return ParseClock(cfg.get("regular_session", {}).get("close", "15:30"))


def HolidayMap(calendar: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = calendar or LoadMarketCalendar()
    return {str(row["date"]): str(row.get("name", "Market Holiday")) for row in cfg.get("holidays", [])}


def SpecialSessionMap(calendar: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    cfg = calendar or LoadMarketCalendar()
    return {str(row["date"]): row for row in cfg.get("special_sessions", [])}


def IsWeekend(ts: datetime) -> bool:
    return ts.weekday() >= 5


def HolidayName(ts: datetime, calendar: dict[str, Any] | None = None) -> str | None:
    return HolidayMap(calendar).get(ts.date().isoformat())


def IsMarketHoliday(ts: datetime, calendar: dict[str, Any] | None = None) -> bool:
    return HolidayName(ts, calendar) is not None


def IsTradingDate(ts: datetime, calendar: dict[str, Any] | None = None) -> bool:
    specials = SpecialSessionMap(calendar)
    if ts.date().isoformat() in specials:
        return True
    return (not IsWeekend(ts)) and (not IsMarketHoliday(ts, calendar))


def IsRegularMarketTime(ts: datetime, calendar: dict[str, Any] | None = None) -> bool:
    cfg = calendar or LoadMarketCalendar()
    specials = SpecialSessionMap(cfg)
    special = specials.get(ts.date().isoformat())
    if special:
        open_time = ParseClock(str(special.get("open", "09:15")))
        close_time = ParseClock(str(special.get("close", "15:30")))
    else:
        open_time = SessionOpen(cfg)
        close_time = SessionClose(cfg)
    return open_time <= ts.time() <= close_time


def IsMarketSession(ts: datetime, calendar: dict[str, Any] | None = None) -> bool:
    return IsTradingDate(ts, calendar) and IsRegularMarketTime(ts, calendar)


def ShouldStartLiveTick(
    ts: datetime,
    *,
    manage_live_tick: bool = True,
    calendar: dict[str, Any] | None = None,
) -> bool:
    if not manage_live_tick or not IsTradingDate(ts, calendar):
        return False
    return ts.time() <= SessionClose(calendar)


def ShouldRunSingleOffmarketCheck(ts: datetime, calendar: dict[str, Any] | None = None) -> bool:
    return (not IsTradingDate(ts, calendar)) or ts.time() > SessionClose(calendar)


def MarketClosedReason(ts: datetime, calendar: dict[str, Any] | None = None) -> str | None:
    holiday = HolidayName(ts, calendar)
    if holiday:
        return f"Market holiday: {holiday}"
    if IsWeekend(ts):
        return "Market is closed today"
    if ts.time() > SessionClose(calendar):
        return "Market is closed for the day"
    if ts.time() < SessionOpen(calendar):
        return "Market has not opened yet"
    return None
