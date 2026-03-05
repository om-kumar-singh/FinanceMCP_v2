"""
Explanation engine for Advisor V2.

Turns numeric metrics and signal information into short,
natural‑language rationales suitable for end‑user display.
"""

from __future__ import annotations

from typing import Any, Dict, List


def summarise_stock_recommendation(payload: Dict[str, Any]) -> Dict[str, Any]:
  """
  Build a structured explanation object for a single‑stock call.

  Expects the dict returned by `score_stock_signal`.
  """
  quote = payload.get("quote") or {}
  ensemble = payload.get("ensemble") or {}
  tech = payload.get("technical_score") or {}
  signal = payload.get("signal") or {}

  symbol = (quote.get("symbol") or payload.get("symbol") or "").replace(".NS", "").replace(".BO", "")
  action = signal.get("action", "hold")
  score = signal.get("score", 50.0)

  exp_ret = ensemble.get("expected_return")
  exp_vol = ensemble.get("expected_volatility")
  conf = (ensemble.get("confidence") or {}).get("label", "unknown")

  drivers: List[str] = []
  if tech.get("details"):
    drivers.extend(tech["details"])
  if exp_ret is not None:
    drivers.append(f"Ensemble expects ~{round(exp_ret * 100, 1)}% move over the chosen horizon.")
  if exp_vol is not None:
    drivers.append(f"Estimated volatility around {round(exp_vol * 100, 1)}% over the horizon.")

  caveats: List[str] = []
  if conf != "high":
    caveats.append("Model confidence is not high; treat this as one input, not a guarantee.")
  if quote.get("marketCap") == "N/A":
    caveats.append("Fundamental data is incomplete; some valuation metrics may be unreliable.")

  if action in {"strong_buy", "buy"}:
    summary = (
      f"{symbol} screens as a {action.replace('_', ' ')} candidate with a composite signal score of "
      f"{round(score, 1)}. Trend and valuation signals are supportive, but you should size positions "
      f"according to your own risk tolerance."
    )
  elif action == "hold":
    summary = (
      f"{symbol} looks fairly balanced on risk‑reward with a neutral signal around {round(score, 1)}. "
      "Maintaining current exposure or waiting for clearer signals is reasonable."
    )
  elif action == "reduce":
    summary = (
      f"Signals for {symbol} tilt cautious (score ~{round(score, 1)}). Gradual profit‑booking or trimming "
      "exposure could reduce downside risk."
    )
  else:
    summary = (
      f"Risk‑reward for {symbol} currently appears unfavourable (signal score ~{round(score, 1)}). "
      "Fresh exposure may not be justified unless fundamentals improve."
    )

  return {
    "summary": summary,
    "drivers": drivers,
    "caveats": caveats,
  }


def summarise_portfolio_recommendation(result: Dict[str, Any]) -> Dict[str, Any]:
  """
  Build a structured explanation for portfolio‑level output from
  `analyse_portfolio_v2`.
  """
  base = result.get("base") or {}
  risk = result.get("risk_metrics") or {}

  summary_data = base.get("portfolio_summary") or {}
  total_ret = summary_data.get("total_return_percent", 0.0)
  sentiment = base.get("overall_sentiment") or ("Profit" if total_ret > 0 else "Loss" if total_ret < 0 else "Flat")

  volatility = risk.get("volatility", 0.0)
  sharpe = risk.get("sharpe", 0.0)
  diversification = risk.get("diversification_score", 0.0)
  max_pos = risk.get("max_position_weight_percent", 0.0)

  bullets: List[str] = []
  bullets.append(f"Overall portfolio is currently in **{sentiment}** territory with total return around {round(total_ret, 2)}%.")
  bullets.append(f"Estimated daily volatility is ~{round(volatility * 100, 2)}% with an approximate Sharpe of {round(sharpe, 2)}.")
  bullets.append(f"Diversification score is {round(diversification, 1)}/100; largest single position is about {round(max_pos, 2)}% of the portfolio.")

  if diversification < 50 or max_pos > 20:
    bullets.append("Risk is concentrated; consider redistributing exposure towards under‑represented sectors or high‑quality broad‑based funds.")
  else:
    bullets.append("Sector allocation looks reasonably balanced; ongoing SIPs and periodic rebalancing should keep risk under control.")

  caveats: List[str] = [
    "Portfolio risk is approximated from price history and does not incorporate intraday liquidity or derivatives exposure.",
    "Sharpe ratio is based on historical behaviour and may change in different market regimes.",
  ]

  return {
    "summary": " ".join(bullets),
    "drivers": bullets,
    "caveats": caveats,
  }

