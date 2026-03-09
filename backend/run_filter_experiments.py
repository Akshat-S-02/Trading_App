"""
Filter isolation experiments for NiftyBreakout v3.
Base: v2 config (or=6, buf=0.25%, cutoff=11:00, no filters OFF)
Then add each professional filter one at a time, and all together.

Filters tested:
  vwap_only    : close > intraday VWAP
  range_only   : OR range < 0.6% of price
  maxvol_only  : entry volume > max(last 10 bars volume)
  all_filters  : all three combined (v3 default)
"""
import logging
logging.basicConfig(level=logging.WARNING)

from research.backtest.engine import BacktestEngine, RiskConfig
from research.strategies.nifty_breakout import NiftyBreakoutStrategy, NiftyBreakoutConfig
from research.backtest.trade_exporter import export_trades_csv
from research.utils.fee_calculator import FeeConfig, SlippageConfig

FEE  = FeeConfig(brokerage_per_order=20.0, stt_sell_pct=0.025, exchange_pct=0.00345,
                 sebi_pct=0.0001, gst_pct=18.0, stamp_pct=0.003)
SLIP = SlippageConfig(ticks=1, tick_size=0.05)
RISK = RiskConfig(capital=100000, risk_pct=1.0, max_positions=1)
DATES = dict(from_date='2025-03-07', to_date='2025-12-31')
SYMBOLS = ['RELIANCE', 'TCS', 'HDFCBANK']

# Base = v2 settings, all filters OFF
BASE_V2 = dict(or_candle_count=6, or_threshold_pct=0.25,
               no_entry_after_hour=11, no_entry_after_minute=0,
               reward_ratio=1.5,
               use_vwap_filter=False, use_or_range_filter=False, use_max_volume_filter=False)

experiments = {
    "v2_base":    NiftyBreakoutConfig(**BASE_V2),
    "vwap_only":  NiftyBreakoutConfig(**{**BASE_V2, "use_vwap_filter": True}),
    "range_only": NiftyBreakoutConfig(**{**BASE_V2, "use_or_range_filter": True}),
    "maxvol_only":NiftyBreakoutConfig(**{**BASE_V2, "use_max_volume_filter": True}),
    "all_v3":     NiftyBreakoutConfig(or_candle_count=6, or_threshold_pct=0.25,
                                       no_entry_after_hour=11, no_entry_after_minute=0,
                                       reward_ratio=1.5,
                                       use_vwap_filter=True, use_or_range_filter=True,
                                       use_max_volume_filter=True),
}

sep = "="*82
row_fmt = "  {exp:<13} {sym:<10} {trades:>5} {wr:>6} {pf:>7} {pnl:>12} {exp_:<11} {dd:>5}"

print("\n" + sep)
print(row_fmt.format(exp="EXPERIMENT", sym="SYMBOL", trades="TRD", wr="WIN%",
                     pf="PF", pnl="NET P&L", exp_="EXPCTANCY", dd="DD%"))
print(sep)

best_results = {}

for exp_name, cfg in experiments.items():
    for sym in SYMBOLS:
        result = BacktestEngine(
            symbols=[sym], timeframe='5m',
            strategy=NiftyBreakoutStrategy(cfg),
            fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
            save_to_db=False, **DATES,
        ).run()
        m = result.metrics
        pf = f"{m['profit_factor']:.3f}" if m['profit_factor'] else " N/A"
        pnl_str = ("+" if m['net_pnl'] >= 0 else "") + f"Rs.{int(m['net_pnl']):,}"
        exp_str = ("+" if m['expectancy'] >= 0 else "") + f"Rs.{int(m['expectancy'])}"
        print(row_fmt.format(
            exp=exp_name, sym=sym,
            trades=m['total_trades'],
            wr=f"{m['win_rate']*100:.1f}%",
            pf=pf,
            pnl=pnl_str,
            exp_=exp_str,
            dd=f"{m['max_drawdown']:.1f}%"
        ))
        if exp_name == "all_v3":
            export_trades_csv(result.trades, f"{sym.lower()}_v3.csv")
    print("-"*82)

print(sep)
print("\nCSVs for all_v3 written: reliance_v3.csv, tcs_v3.csv, hdfcbank_v3.csv")
