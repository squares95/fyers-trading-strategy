from __future__ import annotations


def Strategy(name: str = "G01", **kwargs):
    strategy_name = str(name).strip().upper()
    if strategy_name == "G01":
        from .G01 import G01Strategy

        return G01Strategy(**kwargs)
    raise ValueError(f"Unknown strategy {name!r}. Available strategies: G01")
