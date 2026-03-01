"""
Mutual fund NAV and SIP calculator services.
"""

import requests


MF_API_BASE = "https://api.mfapi.in/mf"


def get_mutual_fund_nav(scheme_code: str) -> dict | None:
    """
    Fetch latest NAV for a mutual fund scheme.

    Args:
        scheme_code: Mutual fund scheme code (e.g., 119551)

    Returns:
        Dict with scheme_code, scheme_name, nav, date, or None on error.
    """
    if not scheme_code or not str(scheme_code).strip():
        return None

    scheme_code = str(scheme_code).strip()
    url = f"{MF_API_BASE}/{scheme_code}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    meta = data.get("meta")
    nav_data = data.get("data")

    if not meta or not nav_data:
        return None

    latest = nav_data[0]
    nav = latest.get("nav")
    date = latest.get("date")

    if not nav or not date:
        return None

    scheme_name = meta.get("scheme_name", "")
    code = meta.get("scheme_code", scheme_code)

    return {
        "scheme_code": str(code),
        "scheme_name": scheme_name,
        "nav": nav,
        "date": date,
    }


def calculate_sip(
    monthly_investment: float,
    years: int,
    annual_return: float,
) -> dict:
    """
    Calculate SIP (Systematic Investment Plan) future value.

    Args:
        monthly_investment: Monthly investment amount (P)
        years: Investment period in years
        annual_return: Expected annual return percentage

    Returns:
        Dict with monthly_investment, years, annual_return, future_value
    """
    r = annual_return / 12 / 100
    n = years * 12

    if r <= 0:
        fv = monthly_investment * n
    else:
        fv = monthly_investment * ((1 + r) ** n - 1) / r * (1 + r)

    return {
        "monthly_investment": monthly_investment,
        "years": years,
        "annual_return": annual_return,
        "future_value": round(fv),
    }
