"""Even-hour IST crawl times, expressed as a GitHub Actions UTC cron.

IST is UTC+5:30. A fire at minute 30 therefore lands on minute 00 six hours
later, which keeps the hour's even/odd parity. 18:30 UTC is 00:00 IST.
00:30 UTC is 06:00 IST. Both are even IST hours. Odd UTC hours would be odd
IST hours (01:00, 03:00, ...) and are not the local routine.

The cron is not enabled in any workflow.
"""
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
# Minute 30 of every even UTC hour. Twelve fires, each an even IST hour.
EVEN_IST_CRON = "30 0,2,4,6,8,10,12,14,16,18,20,22 * * *"


def utc_hours(expression: str = EVEN_IST_CRON) -> list:
    minute, hours, _dom, _month, _dow = expression.split()
    if minute != "30":
        raise ValueError("expected minute 30")
    return [int(hour) for hour in hours.split(",")]


def ist_hours(expression: str = EVEN_IST_CRON, day: int = 8) -> list:
    found = []
    for hour in utc_hours(expression):
        moment = datetime(2026, 11, day, hour, 30, tzinfo=timezone.utc).astimezone(IST)
        found.append((moment.hour, moment.minute))
    return found
