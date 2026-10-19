"""Technical-analysis engine.

Importing this package registers every built-in indicator. Use::

    from megatool import ta
    ta.available()                     # list indicators + metadata
    ta.compute("rsi", {"close": closes}, period=14)
"""

# Importing the modules populates the registry via their @register decorators.
from megatool.ta import (  # noqa: E402,F401
    extra,
    momentum,
    momentum2,
    other,
    trend,
    trend2,
    volatility,
    volatility2,
    volume,
    volume2,
)
from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    available,
    compute,
    crosses_above,
    crosses_below,
    ema,
    get,
    register,
    rolling_mean,
    rolling_std,
    rolling_sum,
    shift,
    true_range,
    wilder_smooth,
)

__all__ = [
    "IndicatorMeta",
    "IndicatorResult",
    "available",
    "compute",
    "crosses_above",
    "crosses_below",
    "ema",
    "get",
    "register",
    "rolling_mean",
    "rolling_std",
    "rolling_sum",
    "shift",
    "true_range",
    "wilder_smooth",
]
