"""Random / statistical-distribution helpers.

Everything routes through a single numpy Generator so runs are reproducible for
a given (seed, workers) configuration. Provides the skewed distributions the
brief asks for: Zipf, power-law, Poisson, Gaussian, and weighted categorical
choice.
"""
from __future__ import annotations

import numpy as np


class RNG:
    """Thin wrapper around numpy.random.Generator with domain helpers."""

    def __init__(self, seed: int):
        self.g = np.random.default_rng(seed)

    # ---- primitives ----------------------------------------------------------
    def random(self, n: int | None = None):
        return self.g.random() if n is None else self.g.random(n)

    def integers(self, low, high=None, size=None):
        return self.g.integers(low, high, size)

    def choice(self, items, size=None, p=None, replace=True):
        idx = self.g.choice(len(items), size=size, p=p, replace=replace)
        if size is None:
            return items[int(idx)]
        return [items[int(i)] for i in idx]

    def weighted_index(self, weights: np.ndarray, size=None) -> int:
        """Sample index/indices proportional to ``weights`` (need not sum to 1)."""
        w = np.asarray(weights, dtype=float)
        w = w / w.sum()
        return self.g.choice(len(w), size=size, p=w)

    # ---- distributions -------------------------------------------------------
    def poisson(self, lam, size=None):
        return self.g.poisson(lam, size)

    def gaussian(self, mu=0.0, sigma=1.0, size=None):
        return self.g.normal(mu, sigma, size)

    def clipped_gaussian(self, mu, sigma, lo, hi, size=None):
        vals = self.g.normal(mu, sigma, size)
        return np.clip(vals, lo, hi)

    def zipf_weights(self, n: int, exponent: float = 1.2) -> np.ndarray:
        """Zipf-like weights over ``n`` ranks: rank r gets weight r**-exponent."""
        ranks = np.arange(1, n + 1, dtype=float)
        return ranks ** (-exponent)

    def power_law_weights(self, n: int, alpha: float = 2.0) -> np.ndarray:
        """Power-law weights; a few items dominate (heavy head)."""
        ranks = np.arange(1, n + 1, dtype=float)
        return ranks ** (-alpha)

    def truncated_power_law_int(self, lo: int, hi: int, alpha: float = 2.5,
                                size=None):
        """Integer draw in [lo, hi] with power-law bias toward ``lo``."""
        vals = np.arange(lo, hi + 1)
        w = self.power_law_weights(len(vals), alpha)
        w = w / w.sum()
        return vals[self.g.choice(len(vals), size=size, p=w)]

    def bernoulli(self, p: float, size=None):
        if size is None:
            return self.g.random() < p
        return self.g.random(size) < p


def hour_from_weights(rng: RNG, hour_weights) -> int:
    """Pick an hour 0..23 from a 24-length weight vector."""
    return int(rng.weighted_index(np.asarray(hour_weights)))


def minute(rng: RNG) -> int:
    return int(rng.integers(0, 60))
