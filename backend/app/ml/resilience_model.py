"""RandomForest-based Financial Shock Resilience model."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Iterable, List, Tuple

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor


# v2: 7 features (added expense_volatility ratio)
_MODEL_PATH = Path(__file__).with_name("resilience_model_v2.pkl")
EXPECTED_FEATURES = 7


def _generate_training_data(n_samples: int = 2000) -> Tuple[np.ndarray, np.ndarray]:
    """Generate synthetic training data for the resilience model (7 features)."""
    X: List[List[float]] = []
    y: List[float] = []

    for _ in range(n_samples):
        income = random.uniform(20_000, 200_000)
        expense_ratio = random.uniform(0.3, 0.8)
        monthly_expenses = income * expense_ratio

        savings_months = random.uniform(1.0, 12.0)
        savings = monthly_expenses * savings_months

        emi_ratio = random.uniform(0.0, 0.4)
        emi = income * emi_ratio

        portfolio_volatility = random.uniform(0.01, 0.05)
        exp_vol_ratio = random.uniform(0.05, 0.25)  # expense_volatility / monthly_expenses
        macro_risk = random.uniform(0.0, 15.0)
        survival_probability = random.uniform(20.0, 100.0)

        savings_ratio = savings / income

        features = [
            savings_ratio,
            expense_ratio,
            emi_ratio,
            portfolio_volatility,
            exp_vol_ratio,
            macro_risk,
            survival_probability,
        ]

        # Rule-based target formula
        score = (
            savings_ratio * 40.0
            + (1.0 - expense_ratio) * 25.0
            + (1.0 - emi_ratio) * 15.0
            + (1.0 - portfolio_volatility * 10.0) * 10.0
            - exp_vol_ratio * 20.0
            + survival_probability * 0.1
            - macro_risk
        )
        score = max(0.0, min(100.0, score))

        X.append(features)
        y.append(score)

    return np.asarray(X, dtype=float), np.asarray(y, dtype=float)


def train_resilience_model(n_samples: int = 2000) -> RandomForestRegressor:
    """Train the RandomForestRegressor and persist it to disk."""
    X, y = _generate_training_data(n_samples=n_samples)

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=6,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X, y)

    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, _MODEL_PATH)
    return model


def load_resilience_model() -> RandomForestRegressor:
    """Load a trained model, training it if the pickle file does not exist."""
    if not _MODEL_PATH.exists():
        return train_resilience_model()
    model = joblib.load(_MODEL_PATH)
    if not isinstance(model, RandomForestRegressor):
        # Re-train if file is corrupted or wrong type
        return train_resilience_model()
    return model


def predict_resilience(features: Iterable[float]) -> float:
    """Predict resilience score given engineered feature vector (7 features).

    The score is clamped to [0, 100] and rounded to 2 decimal places.
    """
    model = load_resilience_model()
    arr = np.asarray(list(features), dtype=float).reshape(1, -1)
    if arr.shape[1] != EXPECTED_FEATURES:
        raise ValueError(f"Expected {EXPECTED_FEATURES} features, got {arr.shape[1]}")
    pred = float(model.predict(arr)[0])
    pred = max(0.0, min(100.0, pred))
    return round(pred, 2)

