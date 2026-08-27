__all__ = ["GoldPaperTrade", "run_once"]


def GoldPaperTrade(*args, **kwargs):
    from .GoldPaperTrader import GoldPaperTrade as _GoldPaperTrade

    return _GoldPaperTrade(*args, **kwargs)


def run_once(*args, **kwargs):
    from .GoldPaperTrader import run_once as _run_once

    return _run_once(*args, **kwargs)


RunOnce = run_once
