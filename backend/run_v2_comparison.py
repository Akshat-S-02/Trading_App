"""
Compare v1 baseline vs v2 (OR=6 candles, buffer=0.25%, cutoff=11:00) across 3 symbols.
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

# v1 config (reproduce baseline)
v1cfg = NiftyBreakoutConfig(or_candle_count=3, or_threshold_pct=0.10,
                             no_entry_after_hour=13, no_entry_after_minute=30)

# v2 config (all 3 improvements)
v2cfg = NiftyBreakoutConfig()  # or_candle_count=6, or_threshold_pct=0.25, no_entry_after=11:00

print("\n" + "="*70)
print(f"  {'SYM':<10} {'VER':<5} {'TRADES':>6} {'WIN%':>6} {'PF':>6} {'NET P&L':>12} {'CHARGES':>10} {'DD%':>6}")
print("="*70)

for label, cfg in [("v1", v1cfg), ("v2", v2cfg)]:
    for sym in SYMBOLS:
        result = BacktestEngine(
            symbols=[sym], timeframe='5m',
            strategy=NiftyBreakoutStrategy(cfg),
            fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
            save_to_db=False, **DATES,
        ).run()
        m = result.metrics
        pf = f"{m['profit_factor']:.3f}" if m['profit_factor'] else "N/A"
        print(
            f"  {sym:<10} {label:<5} {m['total_trades']:>6} "
            f"{m['win_rate']*100:>5.1f}% {pf:>6} "
            f"{'Rs.'+str(int(m['net_pnl'])):>12} "
            f"{'Rs.'+str(int(m['total_charges'])):>10} "
            f"{m['max_drawdown']:>5.1f}%"
        )
        if label == "v2":
            export_trades_csv(result.trades, f"{sym.lower()}_v2.csv")
    print("-"*70)

print("="*70)
print("\nCSVs written: reliance_v2.csv, tcs_v2.csv, hdfcbank_v2.csv")
