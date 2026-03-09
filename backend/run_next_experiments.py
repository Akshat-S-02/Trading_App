"""
Next round of experiments on NiftyBreakout v3.

Base config for all experiments: v2 settings (or=6, buf=0.25%, cutoff=11:00, no filters).
One variable changed per experiment group.

Exp 1 — OR range threshold sweep (0.8 / 1.0 / 1.2%)
Exp 2 — Gap continuation filter (OR_high > prev_day_close)
Exp 3 — Volume filter comparison (avg_mult 1.5x vs max vs ratio2 2.0x)
All    — Best of each combined
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

# v2 base (no filters)
V2 = dict(or_candle_count=6, or_threshold_pct=0.25,
          no_entry_after_hour=11, no_entry_after_minute=0,
          reward_ratio=1.5,
          use_vwap_filter=False, use_or_range_filter=False,
          use_gap_filter=False, volume_filter_mode="avg_mult")

experiments = {}

# --- Exp 1: OR range threshold ---
for pct in [0.8, 1.0, 1.2]:
    experiments[f"OR_range_{pct}%"] = NiftyBreakoutConfig(
        **{**V2, "use_or_range_filter": True, "max_or_range_pct": pct}
    )

# --- Exp 2: Gap continuation ---
experiments["gap_filter"] = NiftyBreakoutConfig(**{**V2, "use_gap_filter": True})

# --- Exp 3: Volume mode ---
for mode in ["avg_mult", "max", "ratio2"]:
    experiments[f"vol_{mode}"] = NiftyBreakoutConfig(**{**V2, "volume_filter_mode": mode})

# --- v2 base for reference ---
experiments["v2_base"] = NiftyBreakoutConfig(**V2)

# --- Combined: best filters together ---
experiments["combined"] = NiftyBreakoutConfig(
    or_candle_count=6, or_threshold_pct=0.25,
    no_entry_after_hour=11, no_entry_after_minute=0,
    reward_ratio=1.5,
    use_or_range_filter=True, max_or_range_pct=1.0,
    use_gap_filter=True,
    volume_filter_mode="ratio2",
    use_vwap_filter=False,
)

sep = "="*84
hdr = f"  {'EXPERIMENT':<15} {'SYM':<10} {'TRD':>5} {'WIN%':>6} {'PF':>7} {'NET P&L':>12} {'EXP':>10} {'DD%':>6}"
row = "  {exp:<15} {sym:<10} {trades:>5} {wr:>6} {pf:>7} {pnl:>12} {exp_:>10} {dd:>6}"

print("\n" + sep)
print(hdr)
print(sep)

prev_group = None
for exp_name, cfg in experiments.items():
    # Determine group prefix for visual separator
    group = exp_name.split("_")[0]
    if prev_group and group != prev_group:
        print("-"*84)
    prev_group = group

    for sym in SYMBOLS:
        result = BacktestEngine(
            symbols=[sym], timeframe='5m',
            strategy=NiftyBreakoutStrategy(cfg),
            fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
            save_to_db=False, **DATES,
        ).run()
        m = result.metrics
        pf_s  = f"{m['profit_factor']:.3f}" if m['profit_factor'] else "  N/A"
        pnl_s = ("+" if m['net_pnl'] >= 0 else "") + f"Rs.{int(m['net_pnl']):,}"
        exp_s = ("+" if m['expectancy'] >= 0 else "") + f"Rs.{int(m['expectancy'])}"
        print(row.format(
            exp=exp_name, sym=sym,
            trades=m['total_trades'],
            wr=f"{m['win_rate']*100:.1f}%",
            pf=pf_s, pnl=pnl_s, exp_=exp_s,
            dd=f"{m['max_drawdown']:.1f}%"
        ))

print(sep)
print("\nDone.")
