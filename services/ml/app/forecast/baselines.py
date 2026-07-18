"""Transparent statistical baselines for the Phase-12 forecast backtest.

A forecast is only trustworthy if it beats a naive baseline. These are the
reference forecasters every model is compared against in the rolling-origin
backtest (doc 02 §4 / doc 05 §6):

  * SeasonalNaiveForecaster — next month = the same calendar month one year ago
    (m=12 seasonal naive). The standard hard-to-beat baseline for monthly series
    with an annual cycle.
  * MovingAverageForecaster — next month = the trailing k-month mean, held flat.
    A smooth level baseline that ignores seasonality.

Both implement the same ``TrajectoryForecaster`` interface as the TimesFM /
seasonal layers, so the backtest treats a baseline and a model identically and
their prediction intervals (fan) are scored for coverage the same way. Bands come
from the in-sample one-step residual sigma and widen with sqrt(horizon).
"""
from __future__ import annotations

import numpy as np

from .timesfm import TrajectoryForecaster, _next_periods

# Standard-normal quantile multipliers for the fan-chart bands (p10..p90).
_Z = {"p10": -1.2816, "p25": -0.6745, "p75": 0.6745, "p90": 1.2816}
_SEASON = 12


def _fan(base: float, sigma: float, step: int, period: str) -> dict:
    """One fan-chart step: non-negative median + widening symmetric bands."""
    band = float(sigma) * np.sqrt(step)
    base = float(max(0.0, base))
    return {"step": step, "period": period, "median": round(base, 2),
            "p10": round(max(0.0, base + _Z["p10"] * band), 2),
            "p25": round(max(0.0, base + _Z["p25"] * band), 2),
            "p75": round(base + _Z["p75"] * band, 2),
            "p90": round(base + _Z["p90"] * band, 2)}


class SeasonalNaiveForecaster(TrajectoryForecaster):
    """y_hat(t+k) = y(t+k-12). Falls back to the last value if the series is
    shorter than one seasonal period."""
    name = "drishti-baseline-seasonal-naive"
    family = "baseline"

    def forecast(self, counts, months, horizon: int) -> list[dict]:
        arr = np.asarray(counts, dtype=float)
        n = len(arr)
        periods = _next_periods(months[-1], horizon)
        # in-sample one-step seasonal-naive residual sigma (t vs t-12)
        if n > _SEASON:
            resid = arr[_SEASON:] - arr[:-_SEASON]
            sigma = float(np.sqrt(np.mean(resid ** 2))) if len(resid) else 0.0
        else:
            sigma = float(arr.std(ddof=0))
        out = []
        for k in range(1, horizon + 1):
            src = n - _SEASON + (k - 1)
            base = float(arr[src]) if 0 <= src < n and n > _SEASON else float(arr[-1])
            out.append(_fan(base, sigma, k, periods[k - 1]))
        return out


class MovingAverageForecaster(TrajectoryForecaster):
    """y_hat(t+k) = mean(last ``window`` observations), held flat across the
    horizon. Bands from the in-sample one-step moving-average residual sigma."""
    family = "baseline"

    def __init__(self, window: int = 3):
        self.window = max(1, int(window))
        self.name = f"drishti-baseline-ma{self.window}"

    def forecast(self, counts, months, horizon: int) -> list[dict]:
        arr = np.asarray(counts, dtype=float)
        n = len(arr)
        w = min(self.window, n)
        base = float(arr[-w:].mean()) if n else 0.0
        periods = _next_periods(months[-1], horizon)
        # in-sample one-step MA residuals: predict y[t] from the prior w values
        resid = [arr[t] - arr[t - w:t].mean() for t in range(w, n)]
        sigma = float(np.sqrt(np.mean(np.square(resid)))) if resid else float(arr.std(ddof=0))
        return [_fan(base, sigma, k, periods[k - 1]) for k in range(1, horizon + 1)]


# Registry consumed by the backtest — the transparent comparators every model
# must be measured against.
def baseline_forecasters() -> dict[str, TrajectoryForecaster]:
    return {
        "seasonal_naive": SeasonalNaiveForecaster(),
        "moving_average_3": MovingAverageForecaster(window=3),
    }
