"""Statistics on a basin-mean climate series.

Two questions get asked of a rainfall record more than any others: is it
trending, and how unusual is this month. Both have standard answers with
standard traps, and both are arithmetic on a series the package already
returns, so neither costs a download.

Nothing here imports scipy. The package does not declare it, and a statistic
that appears only when some other library happens to have pulled scipy in is
worse than one that is always there.
"""

from __future__ import annotations

import math

#: Acklam's rational approximation to the inverse normal CDF, good to about
#: 1e-9 over the whole range, which is far finer than any rainfall record
#: justifies.
_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01)
_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
      3.754408661907416e+00)


def _normal_quantile(p: float) -> float:
    """The z whose normal CDF is ``p``."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"A probability must lie strictly inside (0, 1); got {p}.")
    low, high = 0.02425, 1 - 0.02425
    if p < low:
        q = math.sqrt(-2 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q
                + _C[5]) / ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1)
    if p > high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q
                 + _C[5]) / ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r
            + _A[5]) * q / (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r
                             + _B[4]) * r + 1)


def _normal_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def _as_series(values):
    import pandas as pd

    if isinstance(values, pd.Series):
        return values.dropna()
    if hasattr(values, "to_series"):
        return values.to_series().dropna()
    return pd.Series(values).dropna()


def spi(values, *, scale: int = 3):
    """Standardized Precipitation Index of a monthly rainfall series.

    Each calendar month is ranked against its own history, so a dry March is
    judged against other Marches rather than against the monsoon. The ranking
    is empirical rather than a fitted gamma: a fitted distribution is the
    textbook method and it fails quietly on records with many zero months,
    which is exactly the arid ground where the index matters most.

    ``scale`` is the accumulation window in months. 3 is the usual choice for
    agricultural drought, 12 for hydrological.

    Returns a series of z-scores: below -1 is dry, below -2 severely so.

    One consequence of ranking rather than fitting is worth knowing before
    reading the tails: the most extreme value the index can take is set by the
    length of the record. With forty years behind each calendar month the
    ceiling is about 1.97, so a forty-year record cannot report an SPI of -2
    however dry the month was. Fit a distribution if the tail itself is the
    question; rank if the ordering is.
    """
    import numpy as np
    import pandas as pd

    series = _as_series(values)
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError(
            "SPI needs a series indexed by date; pass what precipitation() "
            "returns rather than a bare array."
        )

    accumulated = series.rolling(int(scale)).sum().dropna()
    out = pd.Series(index=accumulated.index, dtype="float64")

    for month in range(1, 13):
        sample = accumulated[accumulated.index.month == month]
        if len(sample) < 10:
            out.loc[sample.index] = np.nan
            continue
        ranks = sample.rank(method="average")
        # Weibull plotting positions keep the extremes off 0 and 1, where the
        # normal quantile is undefined.
        probabilities = ranks / (len(sample) + 1)
        out.loc[sample.index] = [_normal_quantile(float(p)) for p in probabilities]

    out.name = f"spi{scale}"
    out.attrs["basinkit_method"] = "empirical ranking, Weibull plotting positions"
    return out.sort_index()


def trend(values, *, alpha: float = 0.05) -> dict:
    """Mann-Kendall trend test with Sen's slope.

    Rainfall records are not normal and are full of ties, so the rank-based
    test is the one the literature uses. Ties are corrected for in the
    variance, which matters on records with repeated zero months; leaving that
    out inflates the significance of a trend in arid basins.

    Returns the slope in units per year, the test statistic, the two-sided
    p-value, and whether it clears ``alpha``.
    """
    import numpy as np
    import pandas as pd

    series = _as_series(values)
    y = series.to_numpy(dtype="float64")
    n = y.size
    if n < 10:
        raise ValueError(
            f"A trend test on {n} points says nothing. Mann-Kendall wants at "
            "least ten, and a rainfall record should have hundreds."
        )

    signs = np.sign(y[None, :] - y[:, None])
    s = float(np.triu(signs, 1).sum())

    _, counts = np.unique(y, return_counts=True)
    ties = float((counts * (counts - 1) * (2 * counts + 5)).sum())
    variance = (n * (n - 1) * (2 * n + 5) - ties) / 18.0

    if s > 0:
        z = (s - 1) / math.sqrt(variance)
    elif s < 0:
        z = (s + 1) / math.sqrt(variance)
    else:
        z = 0.0
    p = 2 * (1 - _normal_cdf(abs(z)))

    if isinstance(series.index, pd.DatetimeIndex):
        t = series.index.to_julian_date().to_numpy() / 365.25
        unit = "per year"
    else:
        t = np.arange(n, dtype="float64")
        unit = "per step"
    rows, cols = np.triu_indices(n, 1)
    spans = t[cols] - t[rows]
    usable = spans != 0
    slope = float(np.median((y[cols] - y[rows])[usable] / spans[usable]))

    return {
        "slope": slope,
        "slope_unit": unit,
        "n": int(n),
        "s": s,
        "z": round(z, 4),
        "p_value": round(p, 6),
        "significant": bool(p < alpha),
        "alpha": alpha,
        "direction": "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat",
        "method": "Mann-Kendall with tie correction; Sen's slope",
    }
