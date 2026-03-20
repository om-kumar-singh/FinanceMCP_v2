"""
Market news service using yfinance.
"""

from __future__ import annotations

import datetime as _dt
from typing import List, Dict, Any

from app.utils.yfinance_wrapper import fetch_news
import time as _time


IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))


def _normalize_ticker(ticker: str | None) -> str:
  """
  Normalize human-friendly inputs like 'NSE' or 'BSE' to yfinance symbols.
  Defaults to NIFTY 50 index if nothing provided.
  """
  if not ticker or not str(ticker).strip():
      return "^NSEI"

  t = str(ticker).strip().upper()

  if t in {"NSE", "NIFTY", "NIFTY50", "NIFTY 50"}:
      return "^NSEI"
  if t in {"BSE", "SENSEX"}:
      return "^BSESN"

  return t


def _format_ts_to_ist(epoch_seconds: float | int | None) -> str | None:
  """
  Convert epoch seconds to a readable IST time string.
  """
  if epoch_seconds is None:
      return None
  try:
      dt_utc = _dt.datetime.utcfromtimestamp(float(epoch_seconds)).replace(
          tzinfo=_dt.timezone.utc
      )
      dt_ist = dt_utc.astimezone(IST)
      return dt_ist.strftime("%d %b %Y, %I:%M %p IST")
  except Exception:
      return None


def get_market_news(ticker: str) -> List[Dict[str, Any]]:
  """
  Fetch latest market news for a given ticker using yfinance.

  Args:
      ticker: Stock or index symbol (e.g., RELIANCE.NS, TCS.NS, NSE, BSE)

  Returns:
      List of dicts with: title, publisher, link, publishedAt
  """
  symbol = _normalize_ticker(ticker)
  try:
      raw_news = fetch_news(symbol, ttl=300)
  except Exception:
      return []

  items: List[Dict[str, Any]] = []

  for item in raw_news:
      if not isinstance(item, dict):
          continue

      title = item.get("title")
      link = item.get("link")
      publisher = item.get("publisher") or item.get("provider")
      ts = (
          item.get("providerPublishTime")
          or item.get("published_at")
          or item.get("pubDate")
      )

      if not (title and link and publisher):
          continue

      published_at = None
      if isinstance(ts, (int, float)):
          published_at = _format_ts_to_ist(ts)

      items.append(
          {
              "title": title,
              "publisher": publisher,
              "link": link,
              "publishedAt": published_at,
          }
      )

  # Rotation/jitter: repeated calls should not return identical headlines ordering.
  # Keep it deterministic-ish per time window to aid caching while still varying.
  if len(items) <= 1:
      return items[:20]

  try:
      n = len(items)
      # Change offset roughly every ~45 seconds.
      offset = int((_time.time() // 45) % n)
      rotated = items[offset:] + items[:offset]
      return rotated[:20]
  except Exception:
      return items[:20]

