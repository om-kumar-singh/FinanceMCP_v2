"""
IST (Indian Standard Time) utilities.
"""

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def get_ist_timestamp() -> str:
    """Return current time in IST as a formatted string."""
    return datetime.now(IST).strftime("%d/%m/%Y, %I:%M:%S %p IST")


def get_ist_now():
    """Return current datetime in IST (for date comparisons etc)."""
    return datetime.now(IST)
