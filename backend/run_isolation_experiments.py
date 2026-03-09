"""
Isolation experiments to identify which v2 parameter drove the improvement.

Experiments:
  A  — OR=3, buffer=0.25%, cutoff=11:00   (isolate buffer+cutoff, keep v1 OR)
  B  — OR=6, buffer=0.10%, cutoff=11:00   (isolate OR+cutoff, keep v1 buffer)
  C  — OR=3, buffer=0.10%, cutoff=11:00   (cutoff only — v1 OR and buffer)
  v2 — OR=6, buffer=0.25%, cutoff=11:00   (all three)
  R2 — v2 + reward_ratio=2.0R
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
SYMBOLS = ['RELIANCE', 'TCS', 'HDFCBANK']

experiments = {
    "v1_base": NiftyBreakoutConfig(or_candle_count=3, or_threshold_pct=0.10,
                                    no_entry_after_hour=13, no_entry_after_minute=30,
                                    reward_ratio=1.5),
    "A_buf+cut": NiftyBreakoutConfig(or_candle_count=3, or_threshold_pct=0.25,
                                      no_entry_after_hour=11, no_entry_after_minute=0,
                                      reward_ratio=1.5),
    "B_OR+cut":  NiftyBreakoutConfig(or_candle_count=6, or_threshold_pct=0.10,
                                      no_entry_after_hour=11, no_entry_after_minute=0,
                                      reward_ratio=1.5),
    "C_cut_only": NiftyBreakoutConfig(or_candle_count=3, or_threshold_pct=0.10,
                                       no_entry_after_hour=11, no_entry_after_minute=0,
                                       reward_ratio=1.5),
    "v2_all":    NiftyBreakoutConfig(or_candle_count=6, or_threshold_pct=0.25,
                                      no_entry_after_hour=11, no_entry_after_minute=0,
                                      reward_ratio=1.5),
    "v2+R2":     NiftyBreakoutConfig(or_candle_count=6, or_threshold_pct=0.25,
                                      no_entry_after_hour=11, no_entry_after_minute=0,
                                      reward_ratio=2.0),
}

sep = "="*82
row_fmt = "  {exp:<12} {sym:<10} {trades:>6} {wr:>6} {pf:>7} {pnl:>12} {charges:>10} {dd:>6}"
hdr_fmt = "  {exp:<12} {sym:<10} {trades:>6} {wr:>6} {pf:>7} {pnl:>12} {charges:>10} {dd:>6}"

print("\n" + sep)
print(hdr_fmt.format(exp="EXPERIMENT", sym="SYMBOL", trades="TRD", wr="WIN%",
                     pf="PF", pnl="NET P&L", charges="CHARGES", dd="DD%"))
print(sep)

for exp_name, cfg in experiments.items():
    for sym in SYMBOLS:
        result = BacktestEngine(
            symbols=[sym], timeframe='5m',
            strategy=NiftyBreakoutStrategy(cfg),
            fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
            save_to_db=False, **DATES,
        ).run()
        m = result.metrics
        pf = f"{m['profit_factor']:.3f}" if m['profit_factor'] else "N/A"
        pnl_str = ("+" if m['net_pnl'] >= 0 else "") + f"Rs.{int(m['net_pnl']):,}"
        print(row_fmt.format(
            exp=exp_name, sym=sym,
            trades=m['total_trades'],
            wr=f"{m['win_rate']*100:.1f}%",
            pf=pf,
            pnl=pnl_str,
            charges=f"Rs.{int(m['total_charges']):,}",
            dd=f"{m['max_drawdown']:.1f}%"
        ))
    print("-"*82)

print(sep)
print("\nKey: OR3=3-candle OR (09:15-09:30) | OR6=6-candle OR (09:15-09:45)")
print("     buf=breakout buffer% | cut=entry cutoff time | R=reward ratio")
