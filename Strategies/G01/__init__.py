from __future__ import annotations

from .Strategy import G01Strategy


def Scan(*args, **kwargs):
    return G01Strategy().Scan(*args, **kwargs)


def Backtest(*args, **kwargs):
    return G01Strategy().Backtest(*args, **kwargs)


def PaperTrade(*args, **kwargs):
    return G01Strategy().PaperTrade(*args, **kwargs)


__all__ = ["Backtest", "G01Strategy", "PaperTrade", "Scan"]
