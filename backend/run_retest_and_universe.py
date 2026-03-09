"""
All-in-one experiment runner:
  Part 1: Retest vs Immediate on RELIANCE, TCS, HDFCBANK
           Test retest_window 3 / 5 candles and retest_tolerance 0.05% / 0.10% / 0.15%
  Part 2: 3-universe comparison (all-10 / momentum-5 / banking-3)
           with best_combo config (or_range 1.0% + gap_filter + ratio2 volume)
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

SEP3   = "="*80
ROW    = "  {label:<22} {sym:<11} {t:>5} {wr:>6} {pf:>7} {pnl:>12} {exp_:>10} {dd:>5}"
HEADER = ROW.format(label="EXPERIMENT", sym="SYMBOL", t="TRD", wr="WIN%",
                    pf="PF", pnl="NET P&L", exp_="EXPCTANCY", dd="DD%")

def run(label, cfg, syms):
    rows = []
    for sym in syms:
        r = BacktestEngine(symbols=[sym], timeframe='5m',
                           strategy=NiftyBreakoutStrategy(cfg),
                           fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
                           save_to_db=False, **DATES).run()
        m = r.metrics
        pf  = f"{m['profit_factor']:.3f}" if m['profit_factor'] else "  N/A"
        pnl = ("+" if m['net_pnl'] >= 0 else "") + f"Rs.{int(m['net_pnl']):,}"
        exp = ("+" if m['expectancy'] >= 0 else "") + f"Rs.{int(m['expectancy'])}"
        rows.append(ROW.format(label=label, sym=sym, t=m['total_trades'],
                               wr=f"{m['win_rate']*100:.1f}%", pf=pf, pnl=pnl, exp_=exp,
                               dd=f"{m['max_drawdown']:.1f}%"))
    return rows

BASE_SYMS = ['RELIANCE', 'TCS', 'HDFCBANK']

# ── Base configs ────────────────────────────────────────────────────────────
V2_CFG = dict(entry_mode="immediate", or_candle_count=6, or_threshold_pct=0.25,
              no_entry_after_hour=11, no_entry_after_minute=0, reward_ratio=1.5,
              use_or_range_filter=False, use_gap_filter=False,
              volume_filter_mode="avg_mult", use_vwap_filter=False)

BEST_CFG = {**V2_CFG,
             "use_or_range_filter": True, "max_or_range_pct": 1.0,
             "use_gap_filter": True, "volume_filter_mode": "ratio2"}

# ── PART 1: Retest experiments ──────────────────────────────────────────────
print(f"\n{'#'*80}")
print("# PART 1: Retest Entry vs Immediate")
print(f"{'#'*80}\n")
print(SEP3)
print(HEADER)
print(SEP3)

# Immediate baseline with best filters
all_rows = run("immediate+best", NiftyBreakoutConfig(**BEST_CFG), BASE_SYMS)
for r in all_rows: print(r)
print("-"*80)

# Retest variants
for window in [3, 5]:
    for tol in [0.05, 0.10, 0.15]:
        label = f"retest_w{window}_t{tol}%"
        cfg = NiftyBreakoutConfig(**{**BEST_CFG, "entry_mode": "retest",
                                     "retest_window": window,
                                     "retest_tolerance_pct": tol})
        for r in run(label, cfg, BASE_SYMS): print(r)
    print("-"*80)

print(SEP3)

# ── PART 2: 3-Universe comparison ───────────────────────────────────────────
ALL10   = ['RELIANCE','TCS','HDFCBANK','ICICIBANK','SBIN','LT','AXISBANK','HCLTECH','KOTAKBANK','INFOSYS']
MOM5    = ['RELIANCE','TCS','ICICIBANK','SBIN','KOTAKBANK']
BANK3   = ['HDFCBANK','ICICIBANK','AXISBANK']

print(f"\n{'#'*80}")
print("# PART 2: Universe Comparison (best_combo config)")
print(f"{'#'*80}\n")

for uni_name, syms in [("all10", ALL10), ("momentum5", MOM5), ("banking3", BANK3)]:
    print(f"\n--- Universe: {uni_name} ({len(syms)} symbols) ---")
    print(SEP3)
    print(HEADER)
    print(SEP3)
    pf_vals, pnl_sum, profitable = [], 0, 0
    for sym in syms:
        r = BacktestEngine(symbols=[sym], timeframe='5m',
                           strategy=NiftyBreakoutStrategy(NiftyBreakoutConfig(**BEST_CFG)),
                           fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
                           save_to_db=False, **DATES).run()
        m = r.metrics
        pf  = m['profit_factor']
        pf_s = f"{pf:.3f}" if pf else "  N/A"
        pnl_s = ("+" if m['net_pnl'] >= 0 else "") + f"Rs.{int(m['net_pnl']):,}"
        exp_s = ("+" if m['expectancy'] >= 0 else "") + f"Rs.{int(m['expectancy'])}"
        print(ROW.format(label=uni_name, sym=sym, t=m['total_trades'],
                         wr=f"{m['win_rate']*100:.1f}%", pf=pf_s, pnl=pnl_s,
                         exp_=exp_s, dd=f"{m['max_drawdown']:.1f}%"))
        pnl_sum += m['net_pnl']
        if pf: pf_vals.append(pf)
        if m['net_pnl'] > 0: profitable += 1
    print(SEP3)
    avg_pf = sum(pf_vals)/len(pf_vals) if pf_vals else 0
    print(f"  Universe total P&L: {'+'if pnl_sum>=0 else''}Rs.{int(pnl_sum):,}")
    print(f"  Avg PF: {avg_pf:.3f} | Profitable: {profitable}/{len(syms)} symbols\n")

print("\nDone.")
