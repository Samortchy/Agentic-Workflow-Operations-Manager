"""
clock_checker.py
Custom step — injects the current date/time into the envelope so that downstream
steps (and the LLM extraction prompt) are time-aware. Used by the meeting
scheduler to resolve relative dates such as "next Tuesday" or "tomorrow".

Config (optional)
-----------------
  timezone : IANA tz name (default "UTC").

Output data
-----------
  current_datetime : ISO-8601 string
  current_date     : YYYY-MM-DD
  current_time     : HH:MM
  weekday          : e.g. "Monday"
  timezone         : the tz actually used
"""
from datetime import datetime, timezone as _utc
from ..base_step import BaseStep, StepResult

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


class ClockChecker(BaseStep):

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            tzname = config.get("timezone", "UTC")
            tz = _utc.utc
            if ZoneInfo and tzname != "UTC":
                try:
                    tz = ZoneInfo(tzname)
                except Exception:
                    tzname, tz = "UTC", _utc.utc

            now = datetime.now(tz)
            return StepResult(success=True, error=None, data={
                "current_datetime": now.isoformat(timespec="minutes"),
                "current_date":     now.strftime("%Y-%m-%d"),
                "current_time":     now.strftime("%H:%M"),
                "weekday":          now.strftime("%A"),
                "timezone":         tzname,
            })
        except Exception as e:
            return StepResult(success=False, data={}, error=f"ClockChecker error: {e}")
