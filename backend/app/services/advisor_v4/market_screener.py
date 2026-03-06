"""
Lightweight market screener utilities for chat advisor.

Scans a small universe of major Indian stocks and produces ranked candidates for:
- momentum_scan
- breakout_scan
- mean_reversion_scan
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import anyio
import pandas_ta as ta

from app.services.market_data_service import safe_fetch_history
from app.services.stock_service import calculate_macd, calculate_moving_averages, calculate_rsi
from app.services.advisor_v4.smart_money_tracker import detect_smart_money


UNIVERSE: List[str] = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "SBIN.NS",
    "ICICIBANK.NS",
    "HDFCBANK.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "HCLTECH.NS",
    "TECHM.NS",
]

SECTOR_UNIVERSE: Dict[str, List[str]] = {
    "IT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "TECHM.NS"],
    "BANKING": ["SBIN.NS", "ICICIBANK.NS", "HDFCBANK.NS", "KOTAKBANK.NS"],
    "ENERGY": ["RELIANCE.NS"],
}


def _human_regime(mr: str | None) -> str:
    if not mr:
        return "mixed"
    s = str(mr)
    if "bull" in s:
        return "bullish"
    if "bear" in s:
        return "bearish"
    if "side" in s:
        return "neutral"
    return "mixed"


def _sector_from_symbol(sym: str) -> str:
    for sec, lst in SECTOR_UNIVERSE.items():
        if sym in lst:
            return sec
    return "OTHER"


def _clean(sym: str) -> str:
    return (sym or "").replace(".NS", "").replace(".BO", "")


async def _run_sync_with_timeout(func, *args, timeout_s: float = 12.0, **kwargs):
    try:
        with anyio.fail_after(timeout_s):
            return await anyio.to_thread.run_sync(lambda: func(*args, **kwargs))
    except Exception:
        return None


async def _compute_metrics(symbol: str) -> Dict[str, Any]:
    """
    Compute RSI, MACD, and moving averages for a symbol.
    Each underlying calculation is blocking and is run in a worker thread.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"symbol": symbol, "error": "Invalid symbol"}

    async with anyio.create_task_group() as tg:
        rsi_res: Dict[str, Any] = {}
        macd_res: Dict[str, Any] = {}
        ma_res: Dict[str, Any] = {}

        async def _rsi():
            nonlocal rsi_res
            r = await _run_sync_with_timeout(calculate_rsi, sym, timeout_s=10.0)
            rsi_res = r if isinstance(r, dict) else {"error": "RSI unavailable"}

        async def _macd():
            nonlocal macd_res
            r = await _run_sync_with_timeout(calculate_macd, sym, timeout_s=10.0)
            macd_res = r if isinstance(r, dict) else {"error": "MACD unavailable"}

        async def _ma():
            nonlocal ma_res
            r = await _run_sync_with_timeout(calculate_moving_averages, sym, timeout_s=12.0)
            ma_res = r if isinstance(r, dict) else {"error": "MA unavailable"}

        tg.start_soon(_rsi)
        tg.start_soon(_macd)
        tg.start_soon(_ma)

    return {
        "symbol": sym,
        "rsi": rsi_res,
        "macd": macd_res,
        "ma": ma_res,
    }


async def _macd_bullish_crossover(symbol: str) -> Optional[bool]:
    """
    Detect bullish MACD crossover using last two points:
    yesterday MACD <= Signal and today MACD > Signal.
    """
    hist, resolved_symbol, _err = await _run_sync_with_timeout(safe_fetch_history, symbol, period="60d", timeout_s=12.0)
    if hist is None or "Close" not in getattr(hist, "columns", []):
        return None
    close = hist["Close"].dropna()
    if len(close) < 40:
        return None
    try:
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    except Exception:
        return None
    if macd_df is None or macd_df.empty or len(macd_df) < 2:
        return None
    cols = macd_df.columns.tolist()
    if len(cols) < 2:
        return None
    prev = macd_df.iloc[-2]
    cur = macd_df.iloc[-1]
    try:
        prev_macd = float(prev[cols[0]])
        prev_sig = float(prev[cols[1]])
        cur_macd = float(cur[cols[0]])
        cur_sig = float(cur[cols[1]])
    except Exception:
        return None
    return (prev_macd <= prev_sig) and (cur_macd > cur_sig)


async def _price_crossed_above_sma50(symbol: str) -> Optional[bool]:
    """
    Detect price crossing above SMA50 using last two closes vs last two SMA50 values.
    """
    hist, resolved_symbol, _err = await _run_sync_with_timeout(safe_fetch_history, symbol, period="120d", timeout_s=12.0)
    if hist is None or "Close" not in getattr(hist, "columns", []):
        return None
    close = hist["Close"].dropna()
    if len(close) < 60:
        return None
    try:
        sma50 = ta.sma(close, length=50)
    except Exception:
        return None
    if sma50 is None or sma50.empty or len(sma50) < 2:
        return None
    try:
        prev_close = float(close.iloc[-2])
        cur_close = float(close.iloc[-1])
        prev_sma = float(sma50.iloc[-2])
        cur_sma = float(sma50.iloc[-1])
    except Exception:
        return None
    return (prev_close <= prev_sma) and (cur_close > cur_sma)


@dataclass
class ScanRow:
    symbol: str
    score: int
    rsi: Optional[float]
    above_50: Optional[bool]
    above_200: Optional[bool]
    macd_trend: Optional[str]
    notes: str


@dataclass
class FlowRow:
    symbol: str
    volume_z: Optional[float]
    price_change: Optional[float]
    label: str
    notes: str


def _safe_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def _near_pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """
    Return |a-b|/b as a fraction (e.g. 0.01 == 1% away).
    """
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b)


def _watch_notes(sym: str, metrics: Dict[str, Any]) -> str:
    """
    Build a concise human note for "near-signal" candidates.
    """
    rsi = _safe_float(((metrics.get("rsi") or {}) if isinstance(metrics.get("rsi"), dict) else {}).get("rsi"))
    macd = (metrics.get("macd") or {}) if isinstance(metrics.get("macd"), dict) else {}
    ma = (metrics.get("ma") or {}) if isinstance(metrics.get("ma"), dict) else {}
    price = _safe_float(ma.get("price") or ma.get("current_price"))
    sma50 = _safe_float(ma.get("sma50"))
    hist = _safe_float(macd.get("histogram"))
    macd_trend = macd.get("trend")

    parts: List[str] = []
    if rsi is not None and rsi >= 60:
        parts.append(f"RSI {rsi:.0f}")
    # near SMA50 often acts as near-term "breakout" level for trend resumption
    near = _near_pct(price, sma50)
    if near is not None and near <= 0.012:
        parts.append("trading near 50-day MA")
    if macd_trend == "bullish" and (hist is None or hist >= 0):
        parts.append("MACD bullish")
    elif hist is not None and hist > 0:
        parts.append("MACD momentum improving")
    elif macd_trend == "bearish" and hist is not None and hist > -0.2:
        parts.append("MACD flattening")

    if not parts and rsi is not None:
        parts.append(f"RSI {rsi:.0f}")
    return ", ".join(parts) if parts else "near-signal setup"


def _watch_score(metrics: Dict[str, Any]) -> float:
    """
    Heuristic score for near-signal ranking.
    Higher is better.
    """
    rsi = _safe_float(((metrics.get("rsi") or {}) if isinstance(metrics.get("rsi"), dict) else {}).get("rsi"))
    macd = (metrics.get("macd") or {}) if isinstance(metrics.get("macd"), dict) else {}
    ma = (metrics.get("ma") or {}) if isinstance(metrics.get("ma"), dict) else {}
    price = _safe_float(ma.get("price") or ma.get("current_price"))
    sma50 = _safe_float(ma.get("sma50"))
    hist = _safe_float(macd.get("histogram"))
    macd_trend = macd.get("trend")

    s = 0.0
    if rsi is not None:
        # prioritize RSI strength above 60 for breakout watchlists, but still rank by RSI in general
        s += max(0.0, min(20.0, rsi - 50.0)) / 20.0  # 50→0, 70→1
    near = _near_pct(price, sma50)
    if near is not None:
        # within 3% gets some credit; within 1% gets most credit
        s += max(0.0, 0.03 - near) / 0.03
    if macd_trend == "bullish":
        s += 0.6
    if hist is not None:
        # positive histogram indicates positive momentum
        s += 0.4 if hist > 0 else 0.1 if hist > -0.2 else 0.0
    return s


def _flow_label(z: Optional[float]) -> str:
    if z is None:
        return "unknown"
    if z > 1.5:
        return "strong institutional participation"
    if z > 0.5:
        return "moderate accumulation"
    if z >= -0.5:
        return "normal activity"
    return "weak participation"


async def scan_unusual_volume(limit: int = 5) -> List[FlowRow]:
    rows: List[FlowRow] = []
    for sym in UNIVERSE:
        sm = await _run_sync_with_timeout(detect_smart_money, sym, timeout_s=8.0)
        if not isinstance(sm, dict):
            continue
        z = _safe_float(sm.get("volume_zscore"))
        pc = _safe_float(sm.get("price_change"))
        rows.append(
            FlowRow(
                symbol=sym,
                volume_z=z,
                price_change=pc,
                label=_flow_label(z),
                notes=f"z={z:.2f}" if z is not None else "z=N/A",
            )
        )
    rows = [r for r in rows if r.volume_z is not None]
    rows.sort(key=lambda r: r.volume_z or -999.0, reverse=True)
    return rows[:limit]


async def scan_accumulation(limit: int = 5) -> List[FlowRow]:
    """
    Accumulation when:
    - volume_z_score > 1
    - price_change positive
    """
    out: List[FlowRow] = []
    for sym in UNIVERSE:
        sm = await _run_sync_with_timeout(detect_smart_money, sym, timeout_s=8.0)
        if not isinstance(sm, dict):
            continue
        z = _safe_float(sm.get("volume_zscore"))
        pc = _safe_float(sm.get("price_change"))
        if z is None or pc is None:
            continue
        if z > 1.0 and pc > 0:
            out.append(
                FlowRow(
                    symbol=sym,
                    volume_z=z,
                    price_change=pc,
                    label="accumulation",
                    notes=f"z={z:.2f}, price_change={pc*100:+.2f}%",
                )
            )
    out.sort(key=lambda r: (r.volume_z or 0.0), reverse=True)
    return out[:limit]


async def scan_sector_flow(sector: str) -> List[FlowRow]:
    sec = (sector or "").strip().upper()
    universe = SECTOR_UNIVERSE.get(sec) or []
    out: List[FlowRow] = []
    for sym in universe:
        sm = await _run_sync_with_timeout(detect_smart_money, sym, timeout_s=8.0)
        if not isinstance(sm, dict):
            continue
        z = _safe_float(sm.get("volume_zscore"))
        pc = _safe_float(sm.get("price_change"))
        out.append(
            FlowRow(
                symbol=sym,
                volume_z=z,
                price_change=pc,
                label=_flow_label(z),
                notes=f"z={z:.2f}" if z is not None else "z=N/A",
            )
        )
    out.sort(key=lambda r: (r.volume_z is None, -(r.volume_z or 0.0)))
    return out


@dataclass
class AiSignalRow:
    symbol: str
    expected_return: Optional[float]
    momentum: Optional[float]
    score: float


async def scan_ai_buy_signals(limit: int = 5) -> List[AiSignalRow]:
    """
    AI buy signal screener:
    - prediction score from ensemble_forecast (via ranking engine)
    - simple momentum from MACD trend
    """
    from app.services.prediction_ranking_service import rank_by_expected_return
    from app.services.stock_service import calculate_macd

    ranking = await _run_sync_with_timeout(rank_by_expected_return, UNIVERSE, horizon="short", limit=10, timeout_s=25.0)
    ranked = (ranking or {}).get("ranked") if isinstance(ranking, dict) else None
    if not ranked:
        return []

    rows: List[AiSignalRow] = []
    for row in ranked:
        sym = row.get("symbol")
        if not sym:
            continue
        er = _safe_float(row.get("expected_return"))
        m = await _run_sync_with_timeout(calculate_macd, sym, timeout_s=10.0)
        mom = 0.5
        if isinstance(m, dict) and not m.get("error"):
            trend = m.get("trend")
            if trend == "bullish":
                mom = 1.0
            elif trend == "bearish":
                mom = 0.0
        score = (er or 0.0) + 0.1 * mom
        rows.append(AiSignalRow(symbol=sym, expected_return=er, momentum=mom, score=score))

    rows.sort(key=lambda r: r.score, reverse=True)
    return rows[:limit]


def get_ai_sector_beneficiaries() -> List[Dict[str, str]]:
    """
    Static view of technology leaders likely to benefit from AI adoption.
    """
    return [
        {"symbol": "TCS.NS", "reason": "Large-cap IT services leader with strong AI/cloud capabilities."},
        {"symbol": "INFY.NS", "reason": "Global IT major investing heavily in AI platforms and automation."},
        {"symbol": "HCLTECH.NS", "reason": "IT services and engineering with focus on cloud & AI solutions."},
        {"symbol": "TECHM.NS", "reason": "Technology and telecom-focused IT with exposure to AI/5G themes."},
        {"symbol": "LTIM.NS", "reason": "Digital engineering and analytics player with AI-led transformation offerings."},
    ]


async def generate_market_insights() -> Optional[Dict[str, Any]]:
    """
    Combine market regime + momentum leaders + institutional flow + AI forecast leaders.
    """
    from app.services.advisor_v4.regime_detection import detect_market_regime
    from app.services.prediction_ranking_service import rank_by_expected_return

    regime = await _run_sync_with_timeout(detect_market_regime, "^NSEI", timeout_s=10.0)
    mom = await scan_momentum(limit=3)
    vol = await scan_unusual_volume(limit=5)
    ranking = await _run_sync_with_timeout(rank_by_expected_return, None, horizon="short", limit=3, timeout_s=25.0)

    if not isinstance(regime, dict) and not mom and not vol and not ranking:
        return None

    # Infer sector accumulation from volume scan: sector avg zscore
    sector_scores: Dict[str, List[float]] = {}
    for r in vol or []:
        if r.volume_z is None:
            continue
        sec = _sector_from_symbol(r.symbol)
        sector_scores.setdefault(sec, []).append(float(r.volume_z))
    sector_avg = {k: (sum(v) / len(v)) for k, v in sector_scores.items() if v}
    top_sectors = sorted(sector_avg.items(), key=lambda kv: kv[1], reverse=True)[:2]

    return {
        "market_regime": _human_regime((regime or {}).get("market_regime") if isinstance(regime, dict) else None),
        "regime_raw": regime,
        "momentum_leaders": (mom or {}).get("confirmed") or (mom or {}).get("watchlist") or [],
        "sector_flow": top_sectors,
        "ai_forecast_leaders": (ranking or {}).get("ranked") if isinstance(ranking, dict) else [],
    }


async def generate_market_risk_summary() -> Optional[Dict[str, Any]]:
    """
    Summarise market risks using volatility + weak momentum + negative predictions + lack of accumulation.
    """
    from app.services.advisor_v4.regime_detection import detect_market_regime
    from app.services.prediction_ranking_service import rank_by_expected_return

    regime = await _run_sync_with_timeout(detect_market_regime, "^NSEI", timeout_s=10.0)
    mom = await scan_momentum(limit=5)
    acc = await scan_accumulation(limit=5)
    ranking = await _run_sync_with_timeout(rank_by_expected_return, None, horizon="short", limit=5, timeout_s=25.0)

    return {
        "regime": regime if isinstance(regime, dict) else {},
        "momentum_confirmed": bool((mom or {}).get("confirmed")),
        "accumulation_count": len(acc or []),
        "ai_ranked": (ranking or {}).get("ranked") if isinstance(ranking, dict) else [],
    }


async def generate_market_trend_summary() -> Optional[Dict[str, Any]]:
    """
    Summarise emerging trends using sector flow + momentum leaders + regime.
    """
    from app.services.advisor_v4.regime_detection import detect_market_regime

    regime = await _run_sync_with_timeout(detect_market_regime, "^NSEI", timeout_s=10.0)
    mom = await scan_momentum(limit=3)
    vol = await scan_unusual_volume(limit=8)

    # Sector flow: avg zscore by sector
    sector_scores: Dict[str, List[float]] = {}
    for r in vol or []:
        if r.volume_z is None:
            continue
        sec = _sector_from_symbol(r.symbol)
        sector_scores.setdefault(sec, []).append(float(r.volume_z))
    sector_avg = {k: (sum(v) / len(v)) for k, v in sector_scores.items() if v}
    ordered = sorted(sector_avg.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "regime": regime if isinstance(regime, dict) else {},
        "momentum_leaders": (mom or {}).get("confirmed") or (mom or {}).get("watchlist") or [],
        "sector_flow": ordered,
    }


async def scan_momentum(limit: int = 5) -> Dict[str, List[ScanRow]]:
    """
    Momentum score rules:
    - RSI > 55
    - Price > 50MA
    - MACD bullish
    """
    rows: List[ScanRow] = []
    metrics_by_sym: Dict[str, Dict[str, Any]] = {}
    for sym in UNIVERSE:
        m = await _compute_metrics(sym)
        metrics_by_sym[sym] = m
        rsi = (m.get("rsi") or {}).get("rsi") if isinstance(m.get("rsi"), dict) else None
        macd_trend = (m.get("macd") or {}).get("trend") if isinstance(m.get("macd"), dict) else None
        ma = m.get("ma") if isinstance(m.get("ma"), dict) else {}
        above_50 = (ma or {}).get("signal_sma50") == "above"
        above_200 = (ma or {}).get("signal_sma200") == "above"
        score = 0
        try:
            if rsi is not None and float(rsi) > 55:
                score += 1
        except Exception:
            pass
        if above_50:
            score += 1
        if macd_trend == "bullish":
            score += 1

        notes_parts: List[str] = []
        if rsi is not None:
            notes_parts.append(f"RSI {float(rsi):.0f}")
        if above_50:
            notes_parts.append("above 50-day MA")
        if macd_trend == "bullish":
            notes_parts.append("bullish MACD")
        notes = ", ".join(notes_parts) if notes_parts else "No signal details"

        rows.append(
            ScanRow(
                symbol=sym,
                score=score,
                rsi=float(rsi) if isinstance(rsi, (int, float)) else None,
                above_50=bool(above_50) if above_50 is not None else None,
                above_200=bool(above_200) if above_200 is not None else None,
                macd_trend=str(macd_trend) if macd_trend else None,
                notes=notes,
            )
        )

    rows.sort(key=lambda r: (r.score, r.rsi or 0.0), reverse=True)
    confirmed = [r for r in rows if r.score >= 2][:limit]

    if confirmed:
        return {"confirmed": confirmed, "watchlist": []}

    # Near-signal fallback: top 3 closest momentum candidates
    watch: List[ScanRow] = []
    for sym, m in metrics_by_sym.items():
        if not isinstance(m, dict):
            continue
        note = _watch_notes(sym, m)
        rsi_v = _safe_float(((m.get("rsi") or {}) if isinstance(m.get("rsi"), dict) else {}).get("rsi"))
        watch.append(
            ScanRow(
                symbol=sym,
                score=0,
                rsi=rsi_v,
                above_50=None,
                above_200=None,
                macd_trend=((m.get("macd") or {}) if isinstance(m.get("macd"), dict) else {}).get("trend"),
                notes=note,
            )
        )
    watch.sort(key=lambda r: _watch_score(metrics_by_sym.get(r.symbol, {})), reverse=True)
    return {"confirmed": [], "watchlist": watch[:3]}


async def scan_mean_reversion(limit: int = 5) -> Dict[str, List[ScanRow]]:
    """
    Mean reversion candidates:
    - RSI < 35
    """
    out: List[ScanRow] = []
    all_rows: List[ScanRow] = []
    for sym in UNIVERSE:
        m = await _compute_metrics(sym)
        rsi = (m.get("rsi") or {}).get("rsi") if isinstance(m.get("rsi"), dict) else None
        try:
            rv = float(rsi) if rsi is not None else None
        except Exception:
            rv = None
        if rv is None:
            continue
        all_rows.append(
            ScanRow(
                symbol=sym,
                score=0,
                rsi=rv,
                above_50=None,
                above_200=None,
                macd_trend=(m.get("macd") or {}).get("trend") if isinstance(m.get("macd"), dict) else None,
                notes=f"RSI {rv:.0f}",
            )
        )
        if rv < 35:
            out.append(
                ScanRow(
                    symbol=sym,
                    score=1,
                    rsi=rv,
                    above_50=None,
                    above_200=None,
                    macd_trend=(m.get("macd") or {}).get("trend") if isinstance(m.get("macd"), dict) else None,
                    notes=f"RSI {rv:.0f} (oversold zone)",
                )
            )
    out.sort(key=lambda r: r.rsi or 999.0)
    confirmed = out[:limit]
    if confirmed:
        return {"confirmed": confirmed, "watchlist": []}

    # Near-signal fallback: lowest RSI values closest to oversold
    all_rows.sort(key=lambda r: r.rsi or 999.0)
    watch: List[ScanRow] = []
    for r in all_rows[:3]:
        watch.append(
            ScanRow(
                symbol=r.symbol,
                score=0,
                rsi=r.rsi,
                above_50=None,
                above_200=None,
                macd_trend=r.macd_trend,
                notes=f"RSI {float(r.rsi):.0f} (near oversold)" if (r.rsi is not None and r.rsi < 45) else f"RSI {float(r.rsi):.0f}",
            )
        )
    return {"confirmed": [], "watchlist": watch}


async def scan_breakouts(limit: int = 5) -> Dict[str, List[ScanRow]]:
    """
    Breakout candidates:
    - price crosses above 50MA, OR
    - bullish MACD crossover
    """
    out: List[ScanRow] = []
    metrics_by_sym: Dict[str, Dict[str, Any]] = {}
    for sym in UNIVERSE:
        m = await _compute_metrics(sym)
        metrics_by_sym[sym] = m
        rsi = (m.get("rsi") or {}).get("rsi") if isinstance(m.get("rsi"), dict) else None
        macd = m.get("macd") if isinstance(m.get("macd"), dict) else {}
        ma = m.get("ma") if isinstance(m.get("ma"), dict) else {}

        crossed_50 = await _price_crossed_above_sma50(sym)
        macd_x = await _macd_bullish_crossover(sym)

        if not crossed_50 and not macd_x:
            continue

        notes_parts: List[str] = []
        if crossed_50:
            notes_parts.append("price crossed above 50-day MA")
        if macd_x:
            notes_parts.append("bullish MACD crossover")
        if isinstance(rsi, (int, float)):
            notes_parts.append(f"RSI {float(rsi):.0f}")

        out.append(
            ScanRow(
                symbol=sym,
                score=int(bool(crossed_50)) + int(bool(macd_x)),
                rsi=float(rsi) if isinstance(rsi, (int, float)) else None,
                above_50=(ma.get("signal_sma50") == "above") if isinstance(ma, dict) else None,
                above_200=(ma.get("signal_sma200") == "above") if isinstance(ma, dict) else None,
                macd_trend=macd.get("trend") if isinstance(macd, dict) else None,
                notes=", ".join(notes_parts) if notes_parts else "Breakout signal detected",
            )
        )

    out.sort(key=lambda r: (r.score, r.rsi or 0.0), reverse=True)
    confirmed = out[:limit]
    if confirmed:
        return {"confirmed": confirmed, "watchlist": []}

    # Near-signal fallback: top 3 closest candidates
    watch: List[ScanRow] = []
    for sym, m in metrics_by_sym.items():
        if not isinstance(m, dict):
            continue
        note = _watch_notes(sym, m)
        rsi_v = _safe_float(((m.get("rsi") or {}) if isinstance(m.get("rsi"), dict) else {}).get("rsi"))
        watch.append(
            ScanRow(
                symbol=sym,
                score=0,
                rsi=rsi_v,
                above_50=None,
                above_200=None,
                macd_trend=((m.get("macd") or {}) if isinstance(m.get("macd"), dict) else {}).get("trend"),
                notes=note,
            )
        )
    watch.sort(key=lambda r: _watch_score(metrics_by_sym.get(r.symbol, {})), reverse=True)
    return {"confirmed": [], "watchlist": watch[:3]}

