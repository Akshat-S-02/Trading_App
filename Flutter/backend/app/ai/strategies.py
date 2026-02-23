def evaluate_strategies(ticks: dict):
    """
    ticks = {
       "RELIANCE": {"ltp": 1518.9, "time": 1763..., ...},
       "TCS": {...}
    }
    """
    decisions = {}

    for symbol, t in ticks.items():
        ltp = t["ltp"]

        # Example: simple moving trigger (replace with your actual logic)
        if ltp <= 1000:
            decisions[symbol] = {"action": "buy", "confidence": 0.8}
        elif ltp >= 2000:
            decisions[symbol] = {"action": "sell", "confidence": 0.9}
        else:
            decisions[symbol] = {"action": "hold", "confidence": 0.0}

    return decisions
