"""
10-symbol universe test.
Uses the best-performing combined config from the experiment round:
  OR=6 bars, buf=0.25%, cutoff=11:00
  + OR range filter 1.0%
  + gap filter (OR_high > prev_day_close)
  + volume filter: ratio2 (2x avg)
Also runs v2_base for comparison.
"""
import logging
logging.basicConfig(level=logging.WARNING)

from research.backtest.engine import BacktestEngine, RiskConfig
from research.strategies.nifty_breakout import NiftyBreakoutStrategy, NiftyBreakoutConfig
from research.utils.fee_calculator import FeeConfig, SlippageConfig

FEE  = FeeConfig(brokerage_per_order=20.0, stt_sell_pct=0.025, exchange_pct=0.00345,
                 sebi_pct=0.0001, gst_pct=18.0, stamp_pct=0.003)
SLIP = SlippageConfig(ticks=1, tick_size=0.05)
RISK = RiskConfig(capital=100000, risk_pct=1.0, max_positions=1)
DATES = dict(from_date='2025-03-07', to_date='2025-12-31')

# 10 symbols (INFY not in registry, replaced with WIPRO or skip)
SYMBOLS = ['RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'SBIN',
           'LT', 'AXISBANK', 'HCLTECH', 'KOTAKBANK', 'WIPRO']

v2_cfg = NiftyBreakoutConfig(
    or_candle_count=6, or_threshold_pct=0.25,
    no_entry_after_hour=11, no_entry_after_minute=0,
    reward_ratio=1.5,
    use_or_range_filter=False, use_gap_filter=False,
    volume_filter_mode="avg_mult", use_vwap_filter=False,
)

best_cfg = NiftyBreakoutConfig(
    or_candle_count=6, or_threshold_pct=0.25,
    no_entry_after_hour=11, no_entry_after_minute=0,
    reward_ratio=1.5,
    use_or_range_filter=True, max_or_range_pct=1.0,
    use_gap_filter=True,
    volume_filter_mode="ratio2", volume_ratio_multiplier=2.0,
    use_vwap_filter=False,
)

sep = "="*80
row = "  {sym:<12} {cfg:<10} {t:>5} {wr:>6} {pf:>7} {pnl:>12} {dd:>6}"
print(f"\n{sep}")
print(row.format(sym="SYMBOL", cfg="CONFIG", t="TRD", wr="WIN%", pf="PF", pnl="NET P&L", dd="DD%"))
print(sep)

summary_v2   = {"pf_sum": 0, "pf_n": 0, "profitable": 0, "total": 0}
summary_best = {"pf_sum": 0, "pf_n": 0, "profitable": 0, "total": 0}

for sym in SYMBOLS:
    for label, cfg, summary in [("v2_base", v2_cfg, summary_v2), ("best_combo", best_cfg, summary_best)]:
        result = BacktestEngine(
            symbols=[sym], timeframe='5m',
            strategy=NiftyBreakoutStrategy(cfg),
            fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
            save_to_db=False, **DATES,
        ).run()
        m = result.metrics
        pf = m['profit_factor']
        pf_s = f"{pf:.3f}" if pf else "  N/A"
        pnl_s = ("+" if m['net_pnl'] >= 0 else "") + f"Rs.{int(m['net_pnl']):,}"
        print(row.format(
            sym=sym, cfg=label,
            t=m['total_trades'],
            wr=f"{m['win_rate']*100:.1f}%",
            pf=pf_s, pnl=pnl_s,
            dd=f"{m['max_drawdown']:.1f}%"
        ))
        summary["total"] += 1
        if pf:
            summary["pf_sum"] += pf
            summary["pf_n"] += 1
        if m['net_pnl'] > 0:
            summary["profitable"] += 1
    print()

print(sep)
print(f"\n  {'':12} {'v2_base':>10}   {'best_combo':>10}")
for label, s in [("v2_base", summary_v2), ("best_combo", summary_best)]:
    avg_pf = s["pf_sum"] / s["pf_n"] if s["pf_n"] else 0
    print(f"  Avg PF        {avg_pf:.3f}")
    print(f"  Profitable    {s['profitable']}/{s['total']} symbols")
    break
for s, label in [(summary_v2, "v2_base"), (summary_best, "best_combo")]:
    avg_pf = s["pf_sum"] / s["pf_n"] if s["pf_n"] else 0
    print(f"  {label:<12} avg_PF={avg_pf:.3f}  profitable={s['profitable']}/{s['total']}")
print(sep)
