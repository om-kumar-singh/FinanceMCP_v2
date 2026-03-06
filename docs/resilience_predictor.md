# Financial Resilience Predictor – FinanceMCP

This document describes the **financial resilience prediction system** in the FinanceMCP platform.

The goal of this component is to estimate **how well a person or household can withstand financial shocks**, and to express that as an interpretable **resilience score** with supporting metrics and scenarios.

---

## Problem Statement

Traditional brokerage tools focus on **asset‑level risk** (e.g. volatility of a stock or portfolio).  
The resilience predictor instead focuses on **household‑level resilience**:

- How many months could this person cover their expenses if income stopped?
- How sensitive is their situation to **market drawdowns**?
- How damaging would a **job loss**, **medical emergency**, or **sudden expense** be?
- Which levers (savings, debt, expenses, investments) matter most for their stability?

The output is not a buy/sell signal, but a **summary of financial shock‑absorbing capacity**.

---

## Inputs

The predictor consumes a mix of required and optional inputs.

### Core Inputs

Typical required fields include:

- **Income**
  - Monthly take‑home income (after tax) or an equivalent stable measure.
- **Expenses**
  - Monthly recurring expenses (rent, utilities, groceries, etc.).
- **Savings / Liquid Assets**
  - Emergency fund and other cash‑equivalent balances.
- **Debt / EMIs**
  - Monthly EMIs and loan obligations (home loan, car loan, personal loan, etc.).
- **Employment Stability**
  - High‑level indicator: permanent vs contractual, sector cyclicality, tenure.

### Optional Inputs

Optional inputs can refine the model:

- **Investment portfolio values**
  - Stock portfolio market value.
  - Mutual fund / ETF holdings.
- **Volatility proxies**
  - Past expense history (variance of monthly spending).
  - Asset‑level volatility from market data (e.g. stock symbols, mutual fund schemes).
- **Profile metadata**
  - Age band, dependents, geographic location (for scenario tuning).

The backend aggregates these into a unified feature vector for the ML model and simulators.

---

## Model Overview

The resilience predictor is implemented as a **hybrid system**:

1. **Analytical core**
   - Simple, interpretable formulas for:
     - runway (months of expenses covered by savings)
     - EMI burden
     - basic coverage ratios.
2. **Simulation layer**
   - Monte Carlo style simulations of shocks (market crash, job loss, emergencies).
3. **Machine‑learning layer**
   - A regression model (e.g. RandomForestRegressor) trained on synthetic or anonymized data to approximate complex interactions.
4. **Macro / sentiment overlay**
   - Optional adjustment based on macro indicators and recent market news.

The final **resilience score** is a blend of these views, bounded to a 0–100 scale.

---

## Feature Engineering

Some example engineered features used by the ML model and analytics:

- **Runway months**
  - `runway = savings / monthly_expenses`
- **Savings ratio**
  - `savings_ratio = savings / max(1, monthly_expenses * 6)`  
  (roughly: how close to a six‑month emergency fund target).
- **EMI / income ratio**
  - `emi_ratio = emi / max(1, income)`
- **Expense / income ratio**
  - `expense_ratio = monthly_expenses / max(1, income)`
- **Shock‑adjusted runway (market)**
  - Estimate a portfolio drawdown (e.g. ‑20% to ‑40% depending on volatility and regime).
  - Recompute runway using reduced portfolio value.
- **Shock‑adjusted runway (job loss)**
  - Simulate loss of income for N months; recompute survival distribution using savings and any investment liquidation assumptions.
- **Volatility features (optional)**
  - Standard deviation of expense history.
  - Historical volatility of stocks / funds in the portfolio.
- **Macro stress features (optional)**
  - Derived from inflation, repo rate cycles, market regime, and negative news counts.

These features are fed both into the deterministic analytics and the ML regressors.

---

## Machine‑Learning Model

The ML component is typically a **tree‑based regressor** such as a `RandomForestRegressor`:

- **Inputs**: engineered features derived from income, expenses, savings, debt, portfolio composition, and macro context.
- **Target**: a synthetic or empirically derived **“resilience score”** that encodes:
  - probability of meeting obligations over a future horizon (e.g. 6–12 months),
  - severity of shortfall in adverse scenarios,
  - quality of emergency fund and debt structure.

### Training Process (Conceptual)

1. **Synthetic population generation**
   - Generate a wide range of financial profiles with different incomes, expenses, debts, savings, and volatility patterns.
2. **Scenario simulation**
   - For each synthetic profile, run Monte Carlo simulations of shocks:
     - job loss timing and duration,
     - market drawdowns,
     - random emergency expenses.
3. **Label creation**
   - Compute outcome statistics:
     - median survival months,
     - worst‑case survival,
     - probability of surviving a given horizon (e.g. 6 months).
   - Convert these into a **single resilience label** (0–100).
4. **Model fitting**
   - Fit the regressor to map engineered features → resilience label.
5. **Validation**
   - Check monotonic behavior: better savings, lower EMIs, and higher runway should generally imply higher resilience.

In production, the analytical metrics (runway, ratios, scenario outcomes) are kept visible to avoid the model becoming a black box.

---

## Simulation and Scenario Engine

Beyond a single score, the predictor exposes **scenario‑specific metrics**:

- **Base case**
  - `runway_months` under current income and expense assumptions.
- **Market shock scenario**
  - Apply a drawdown to portfolio values (e.g. market crash).
  - Recompute `adjusted_runway_after_market_shock`.
- **Job loss scenario**
  - Assume no income for a horizon (e.g. 3–12 months).
  - Estimate:
    - median survival months,
    - worst‑case survival,
    - probability of surviving at least 6 months.
- **Emergency expense scenario**
  - Inject one‑off expenses (e.g. medical or family emergency) and recompute resilience.

These scenarios are often implemented via Monte Carlo simulation over many paths, aggregating results into summary statistics.

---

## Macro and Sentiment Overlay

To avoid treating the household in isolation, the predictor can incorporate **macro stress**:

- Inflation trends (high vs moderate vs low).
- Interest‑rate environment (especially for heavily indebted households).
- Market regime (bull vs bear vs sideways).
- Headline sentiment around the economy or job markets.

This layer typically:

- Counts negative‑keyword occurrences in recent news.
- Clips any adjustments to avoid overreacting to noise.
- Slightly reduces resilience scores in stressed regimes and increases them in benign ones.

The overlay is designed to be **additive and explainable**, not a hidden magic factor.

---

## Output and Interpretation

The API returns a structured response that usually includes:

- **Overall score**
  - `resilience_score` (0–100) or `combined_resilience_score`.
  - Higher values indicate better ability to absorb shocks.
- **Risk band**
  - e.g. `Strong`, `Moderate`, `Vulnerable`, `High Risk`.
- **Runway metrics**
  - `runway_months` under base assumptions.
  - Scenario‑specific runways after simulated shocks.
- **Shock metrics**
  - `median_survival_months`.
  - `worst_case_survival_months`.
  - `survival_probability_6_months`.
- **Macro stress indicators**
  - simple flags or scales summarizing macro risk.
- **Recommendations (optional)**
  - scenario‑grouped recommendations (normal times, market crash, job loss, emergency).
  - can be enriched with LLM‑generated tips when keys are configured.

### How Users Should Read the Score

- **80–100 (“Strong”)**
  - Good or excellent emergency buffer.
  - EMIs and expenses are well aligned with income.
  - Multiple shocks are unlikely to cause immediate distress.
- **60–80 (“Moderate”)**
  - Reasonable resilience but some weaknesses (e.g. high EMI ratio or limited buffer).
  - A few targeted improvements (e.g. building 3–6 months of expenses) can substantially de‑risk the situation.
- **40–60 (“Vulnerable”)**
  - Thin margin for error; one or two shocks could cause meaningful strain.
  - Often driven by low savings, high EMIs, or volatile income.
- **0–40 (“High Risk”)**
  - Very limited shock‑absorbing capacity.
  - Immediate focus should be on reducing expenses, building a basic emergency fund, or restructuring debt.

The numeric score should always be interpreted **alongside the detailed metrics** and recommendations, not in isolation.

---

## How This Helps Users

The resilience predictor provides:

- A **single, interpretable metric** for overall financial resilience.
- A breakdown of **why** the score looks the way it does (runway, EMIs, shocks).
- Scenario‑based insights that answer questions like:
  - “What happens if markets fall 30%?”
  - “How long could I survive a job loss?”
  - “How exposed am I to one‑off emergencies?”
- A baseline for **improvement planning**, such as:
  - building a 3–6 month emergency fund,
  - lowering EMIs relative to income,
  - diversifying investments,
  - adjusting lifestyle expenses.

Because it is modular and explainable, this system can be extended or re‑trained as more real‑world data becomes available, while preserving a stable API contract for the rest of the FinanceMCP platform.

