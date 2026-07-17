from strategy.trend_following import TrendFollowingStrategy


STRATEGIES = {
    "trend_following": TrendFollowingStrategy,
}


def get_strategy(name: str):
    try:
        return STRATEGIES[name]
    except KeyError as exc:
        available = ", ".join(sorted(STRATEGIES))
        raise ValueError(f"未知策略: {name}，可用策略: {available}") from exc
