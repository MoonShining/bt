from strategy.dual_momentum_rotation import DualMomentumRotationStrategy
from strategy.indicators import RSRSIndicator, SlopeMomentumIndicator
from strategy.mean_reversion import MeanReversionStrategy
from strategy.trend_following import TrendFollowingStrategy


STRATEGIES = {
    "dual_momentum_rotation": DualMomentumRotationStrategy,
    "mean_reversion": MeanReversionStrategy,
    "trend_following": TrendFollowingStrategy,
}


def get_strategy(name: str):
    try:
        return STRATEGIES[name]
    except KeyError as exc:
        available = ", ".join(sorted(STRATEGIES))
        raise ValueError(f"未知策略: {name}，可用策略: {available}") from exc
