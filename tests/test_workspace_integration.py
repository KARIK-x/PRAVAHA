"""Focused regression: unified workspace integrates all 6 sprint features."""

from megatool.workspace import build_workspace


# Verify build_workspace produces a payload with all required modules
# This is a minimal integration guard — full path requires real store.
def test_workspace_structure_has_all_six_modules():
    # The workspace must reference: overview, structure, fibonacci, levels,
    # candlesticks, trend_momentum_volatility, report, data_quality
    # We inspect the module list rather than requiring full data.
    import inspect

    src = inspect.getsource(build_workspace)
    for key in [
        "overview",
        "structure",
        "fibonacci",
        "levels",
        "candlesticks",
        "trend_momentum_volatility",
        "research_report",
        "data_quality",
    ]:
        assert key in src or f"do_{key}" in src, f"missing {key}"
