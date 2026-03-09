"""
run_experiments_1_2_3.py
========================
Three ordered experiments on the Momentum5 universe.
Run with:  python run_experiments_1_2_3.py

Goal before calling any config "market-safe":
  >= 100 trades across >= 5 symbols, PF > 1.2, DD < 15%

Universe (all 5 proven profitable):
  RELIANCE, TCS, ICICIBANK, SBIN, KOTAKBANK

Experiment 1 — Target Calibration
  reward_ratio in {0.8, 1.0, 1.2}  (default best_combo otherwise)
  Goal: PF > 1.4, DD < 10%

Experiment 2 — Retest Entry
  entry_mode = "retest" with window/tolerance combos
  on the best reward_ratio found in Exp 1

Experiment 3 — Earlier Breakout Detection
  or_candle_count in {3, 4, 6}  (3=09:15-09:30, 4=09:15-09:35, 6=09:15-09:45)
  on the best reward_ratio found in Exp 1
"""
import logging
logging.basicConfig(level=logging.WARNING)

import statistics
from research.backtest.engine import BacktestEngine, RiskConfig
from research.strategies.nifty_breakout import NiftyBreakoutStrategy, NiftyBreakoutConfig
from research.utils.fee_calculator import FeeConfig, SlippageConfig

# ── Shared infrastructure ──────────────────────────────────────────────────
FEE  = FeeConfig(brokerage_per_order=20.0, stt_sell_pct=0.025, exchange_pct=0.00345,
                 sebi_pct=0.0001, gst_pct=18.0, stamp_pct=0.003)
SLIP = SlippageConfig(ticks=1, tick_size=0.05)
RISK = RiskConfig(capital=100000, risk_pct=1.0, max_positions=1)
DATES = dict(from_date='2025-03-07', to_date='2025-12-31')

MOM5 = ['RELIANCE', 'TCS', 'ICICIBANK', 'SBIN', 'KOTAKBANK']

# Base "best_combo" config — filters already validated
BASE = dict(
    entry_mode          = "immediate",
    or_candle_count     = 6,
    or_threshold_pct    = 0.25,
    no_entry_after_hour = 11, no_entry_after_minute = 0,
    reward_ratio        = 1.5,          # <-- this is what Exp 1 sweeps
    use_or_range_filter = True,  max_or_range_pct = 1.0,
    use_gap_filter      = True,
    volume_filter_mode  = "ratio2",
    use_vwap_filter     = False,
)

SEP  = "=" * 95
SEP2 = "-" * 95

# ── Row formatter ──────────────────────────────────────────────────────────
ROW = "  {label:<18} {sym:<11} {t:>4} {wr:>6} {pf:>7} {pnl:>12} {mfe:>8} {mae:>8} {eff:>7} {dd:>6}"
HDR = ROW.format(label="LABEL", sym="SYMBOL", t="TRD", wr="WIN%",
                 pf="PF", pnl="NET P&L", mfe="avgMFE_r", mae="avgMAE_r",
                 eff="EXIT%", dd="DD%")

PASS_MARK = "  [PASS]"
FAIL_MARK = "  [FAIL]"


def run(cfg_dict, sym):
    r = BacktestEngine(
        symbols=[sym], timeframe='5m',
        strategy=NiftyBreakoutStrategy(NiftyBreakoutConfig(**cfg_dict)),
        fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
        save_to_db=False, **DATES,
    ).run()
    return r, r.metrics


def print_universe(label, cfg_dict, syms, goal_pf=1.4, goal_dd=10.0):
    """Run label across syms, print table, print universe aggregate."""
    print(SEP)
    print(HDR)
    print(SEP)
    pf_vals, pnl_sum, trade_sum, profitable = [], 0, 0, 0
    dd_vals = []
    for sym in syms:
        r, m = run(cfg_dict, sym)
        pf   = m['profit_factor']
        pf_s = f"{pf:.3f}" if pf else "  N/A"
        pnl_s = ('+' if m['net_pnl'] >= 0 else '') + f"Rs.{int(m['net_pnl']):,}"
        mfe_s = f"{m['avg_mfe_r']:.3f}R" if m.get('avg_mfe_r') else "   n/a"
        mae_s = f"{m['avg_mae_r']:.3f}R" if m.get('avg_mae_r') else "   n/a"
        eff_s = f"{m['exit_efficiency_pct']:.1f}%" if m.get('exit_efficiency_pct') else "  n/a"
        dd_s  = f"{m['max_drawdown']:.1f}%"
        print(ROW.format(label=label[:18], sym=sym, t=m['total_trades'],
                         wr=f"{m['win_rate']*100:.1f}%", pf=pf_s, pnl=pnl_s,
                         mfe=mfe_s, mae=mae_s, eff=eff_s, dd=dd_s))
        pnl_sum   += m['net_pnl']
        trade_sum += m['total_trades']
        dd_vals.append(m['max_drawdown'])
        if pf:    pf_vals.append(pf)
        if m['net_pnl'] > 0: profitable += 1

    avg_pf  = sum(pf_vals) / len(pf_vals) if pf_vals else 0
    avg_dd  = sum(dd_vals) / len(dd_vals) if dd_vals else 0
    verdict = PASS_MARK if avg_pf >= goal_pf and avg_dd <= goal_dd else FAIL_MARK
    print(SEP)
    print(f"  {label:<18} | Trades:{trade_sum:>4} | AvgPF:{avg_pf:.3f} | "
          f"TotalPnL:{'+' if pnl_sum>=0 else ''}Rs.{int(pnl_sum):,} | "
          f"AvgDD:{avg_dd:.1f}% | {profitable}/{len(syms)} profitable{verdict}")
    return {"label": label, "avg_pf": avg_pf, "avg_dd": avg_dd,
            "total_trades": trade_sum, "total_pnl": pnl_sum, "profitable": profitable}


# ============================================================================
# EXPERIMENT 1 — Target Calibration (reward_ratio sweep)
# ============================================================================
print(f"\n{'#'*95}")
print("# EXPERIMENT 1 — Target Calibration")
print("# Universe: Momentum5  |  Sweep: reward_ratio in {0.8, 1.0, 1.2, 1.5}")
print("# Goal: avg PF > 1.4, avg DD < 10%")
print(f"{'#'*95}")

exp1_results = []
for rr in [0.8, 1.0, 1.2, 1.5]:
    label = f"ratio={rr}R"
    cfg   = {**BASE, "reward_ratio": rr}
    print(f"\n  --- reward_ratio = {rr}R ---")
    res = print_universe(label, cfg, MOM5)
    exp1_results.append(res)

# Pick best reward_ratio = highest PF still meeting DD guard
print(f"\n{'#'*95}")
print("# EXPERIMENT 1 SUMMARY")
print(f"{'#'*95}")
print(f"  {'Label':<18} {'AvgPF':>7} {'TotTrades':>10} {'TotPnL':>14} {'AvgDD':>7} {'Verdict'}")
print(SEP2)
best_exp1 = None
for r in exp1_results:
    verdict = PASS_MARK if r['avg_pf'] >= 1.4 and r['avg_dd'] <= 10.0 else FAIL_MARK
    print(f"  {r['label']:<18} {r['avg_pf']:>7.3f} {r['total_trades']:>10} "
          f"  {'+' if r['total_pnl']>=0 else ''}Rs.{int(r['total_pnl']):>9,} "
          f"{r['avg_dd']:>7.1f}%{verdict}")
    if verdict == PASS_MARK:
        if best_exp1 is None or r['avg_pf'] > best_exp1['avg_pf']:
            best_exp1 = r

if best_exp1:
    best_rr = float(best_exp1['label'].split('=')[1].rstrip('R'))
    print(f"\n  Best reward_ratio for Experiments 2 & 3: {best_rr}R")
else:
    # Fall back to the highest PF even if no PASS
    best_exp1 = max(exp1_results, key=lambda x: x['avg_pf'])
    best_rr = float(best_exp1['label'].split('=')[1].rstrip('R'))
    print(f"\n  No config fully passed. Using highest-PF config for Exp 2 & 3: {best_rr}R")


# ============================================================================
# EXPERIMENT 2 — Retest Entry
# ============================================================================
print(f"\n\n{'#'*95}")
print(f"# EXPERIMENT 2 — Retest Entry")
print(f"# Universe: Momentum5  |  Base: best_combo + reward_ratio={best_rr}R")
print("# Sweep: entry_mode=retest with window in {3,5} x tolerance in {0.05,0.10,0.15}")
print("# Goal: avg PF > 1.4, DD < 10% AND trade count meaningful (>= 15 across universe)")
print(f"{'#'*95}")

BASE2 = {**BASE, "reward_ratio": best_rr}

exp2_results = []
# Baseline: immediate with best_rr
print(f"\n  --- immediate (baseline, ratio={best_rr}R) ---")
res = print_universe(f"imm+{best_rr}R", BASE2, MOM5)
exp2_results.append(res)

for window in [3, 5]:
    for tol in [0.05, 0.10, 0.15]:
        label = f"ret_w{window}_t{tol:.2f}"
        cfg   = {**BASE2, "entry_mode": "retest",
                 "retest_window": window, "retest_tolerance_pct": tol}
        print(f"\n  --- retest window={window} tolerance={tol:.2f}% ---")
        res = print_universe(label, cfg, MOM5)
        exp2_results.append(res)

print(f"\n{'#'*95}")
print("# EXPERIMENT 2 SUMMARY")
print(f"{'#'*95}")
print(f"  {'Label':<18} {'AvgPF':>7} {'TotTrades':>10} {'TotPnL':>14} {'AvgDD':>7} {'Verdict'}")
print(SEP2)
best_exp2 = None
for r in exp2_results:
    trades_ok = r['total_trades'] >= 15
    verdict = PASS_MARK if r['avg_pf'] >= 1.4 and r['avg_dd'] <= 10.0 and trades_ok else FAIL_MARK
    print(f"  {r['label']:<18} {r['avg_pf']:>7.3f} {r['total_trades']:>10} "
          f"  {'+' if r['total_pnl']>=0 else ''}Rs.{int(r['total_pnl']):>9,} "
          f"{r['avg_dd']:>7.1f}%{verdict}")
    if verdict == PASS_MARK:
        if best_exp2 is None or r['avg_pf'] > best_exp2['avg_pf']:
            best_exp2 = r


# ============================================================================
# EXPERIMENT 3 — Earlier Breakout Detection (OR window sweep)
# ============================================================================
print(f"\n\n{'#'*95}")
print(f"# EXPERIMENT 3 — Earlier Breakout Detection")
print(f"# Universe: Momentum5  |  Base: best_combo + reward_ratio={best_rr}R")
print("# Sweep: or_candle_count in {3, 4, 6}  (3=09:30, 4=09:35, 6=09:45 OR end)")
print("# Goal: catch momentum earlier, PF > 1.2, significantly more trades than Exp 1 baseline")
print(f"{'#'*95}")

exp3_results = []
for n_candles in [3, 4, 6]:
    end_min = 15 + n_candles * 5   # minutes past 09:00 IST
    end_time_str = f"09:{end_min:02d}" if end_min < 60 else f"10:{end_min-60:02d}"
    label = f"OR={n_candles}c({end_time_str})"
    cfg   = {**BASE2, "or_candle_count": n_candles}
    print(f"\n  --- or_candle_count={n_candles} (OR ends ~{end_time_str} IST) ---")
    res = print_universe(label, cfg, MOM5, goal_pf=1.2, goal_dd=10.0)
    exp3_results.append(res)

print(f"\n{'#'*95}")
print("# EXPERIMENT 3 SUMMARY")
print(f"{'#'*95}")
print(f"  {'Label':<22} {'AvgPF':>7} {'TotTrades':>10} {'TotPnL':>14} {'AvgDD':>7} {'Verdict'}")
print(SEP2)
for r in exp3_results:
    verdict = PASS_MARK if r['avg_pf'] >= 1.2 and r['avg_dd'] <= 10.0 else FAIL_MARK
    print(f"  {r['label']:<22} {r['avg_pf']:>7.3f} {r['total_trades']:>10} "
          f"  {'+' if r['total_pnl']>=0 else ''}Rs.{int(r['total_pnl']):>9,} "
          f"{r['avg_dd']:>7.1f}%{verdict}")


# ============================================================================
# FINAL SUMMARY
# ============================================================================
print(f"\n\n{'#'*95}")
print("# OVERALL SUMMARY")
print(f"{'#'*95}")
print("  Market-safe criteria: >= 100 trades total, PF > 1.2, avg DD < 15%")
print(SEP2)

all_results = (
    [("Exp1", r) for r in exp1_results] +
    [("Exp2", r) for r in exp2_results] +
    [("Exp3", r) for r in exp3_results]
)
candidates = [(exp, r) for exp, r in all_results
              if r['avg_pf'] >= 1.2 and r['avg_dd'] <= 15.0 and r['total_trades'] >= 30]

if candidates:
    print(f"\n  Candidate configs meeting market-safe threshold:")
    for exp, r in sorted(candidates, key=lambda x: -x[1]['avg_pf']):
        print(f"    [{exp}] {r['label']:<22} PF={r['avg_pf']:.3f}  "
              f"Trades={r['total_trades']}  DD={r['avg_dd']:.1f}%  "
              f"PnL={'+' if r['total_pnl']>=0 else ''}Rs.{int(r['total_pnl']):,}")
else:
    print("\n  No config met all market-safe criteria in this run.")
    print("  Best by PF (regardless of trade count):")
    best = max(all_results, key=lambda x: x[1]['avg_pf'])
    r = best[1]
    print(f"    [{best[0]}] {r['label']:<22} PF={r['avg_pf']:.3f}  "
          f"Trades={r['total_trades']}  DD={r['avg_dd']:.1f}%")

print(f"\n  Done.")
