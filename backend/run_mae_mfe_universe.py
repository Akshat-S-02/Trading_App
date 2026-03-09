"""
run_mae_mfe_universe.py

Combined experiment: MAE/MFE diagnostics + universe testing.

Part 1 – MAE/MFE Analysis (RELIANCE, TCS, HDFCBANK)
  Runs the best_combo config and prints per-trade MAE/MFE R-multiples plus
  aggregate diagnostics.

  Key metrics:
    avg_mfe_r         — average max favourable move  (if low → target too large / entry too late)
    avg_mae_r         — average max adverse move      (if > 1.0 → stop too large)
    entry_too_late_%  — % trades where MFE < 0.5R   (price never really moved for us)
    stop_too_large_%  — % trades where MAE > 1.0R   (stop being crossed on retracements)
    exit_efficiency_% — avg % of MFE actually captured

Part 2 – Universe Test (10 symbols, best_combo config)
  Aggregates total PnL, avg PF, profitable symbols count.

Part 3 – Retest vs Immediate (best_combo config)
  Compares immediate breakout entry to retest-confirmed entry.
"""
import logging
logging.basicConfig(level=logging.WARNING)

import statistics
from research.backtest.engine import BacktestEngine, RiskConfig
from research.strategies.nifty_breakout import NiftyBreakoutStrategy, NiftyBreakoutConfig
from research.utils.fee_calculator import FeeConfig, SlippageConfig

# ── Shared config ────────────────────────────────────────────────────────────
FEE  = FeeConfig(brokerage_per_order=20.0, stt_sell_pct=0.025, exchange_pct=0.00345,
                 sebi_pct=0.0001, gst_pct=18.0, stamp_pct=0.003)
SLIP = SlippageConfig(ticks=1, tick_size=0.05)
RISK = RiskConfig(capital=100000, risk_pct=1.0, max_positions=1)
DATES = dict(from_date='2025-03-07', to_date='2025-12-31')

BASE_SYMS  = ['RELIANCE', 'TCS', 'HDFCBANK']
ALL10      = ['RELIANCE','TCS','HDFCBANK','ICICIBANK','SBIN','LT','AXISBANK','HCLTECH','KOTAKBANK','INFOSYS']
MOM5       = ['RELIANCE','TCS','ICICIBANK','SBIN','KOTAKBANK']
BANK3      = ['HDFCBANK','ICICIBANK','AXISBANK']

# best_combo: OR range 1% + gap filter + ratio2 volume filter
BEST_CFG = dict(
    entry_mode="immediate",
    or_candle_count=6, or_threshold_pct=0.25,
    no_entry_after_hour=11, no_entry_after_minute=0,
    reward_ratio=1.5,
    use_or_range_filter=True, max_or_range_pct=1.0,
    use_gap_filter=True,
    volume_filter_mode="ratio2",
    use_vwap_filter=False,
)

SEP  = "=" * 90
SEP2 = "-" * 90


def run_one(cfg_dict, sym):
    """Run backtest for single symbol, return (result, metrics)."""
    r = BacktestEngine(
        symbols=[sym], timeframe='5m',
        strategy=NiftyBreakoutStrategy(NiftyBreakoutConfig(**cfg_dict)),
        fee_config=FEE, slippage_config=SLIP, risk_config=RISK,
        save_to_db=False, **DATES,
    ).run()
    return r, r.metrics


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 – MAE / MFE Analysis
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'#'*90}")
print("# PART 1: MAE / MFE Diagnostics  [config: best_combo]")
print(f"{'#'*90}\n")

ALL_TRADES = []

for sym in BASE_SYMS:
    result, m = run_one(BEST_CFG, sym)
    trades = result.trades
    ALL_TRADES.extend(trades)

    if not trades:
        print(f"  {sym}: 0 trades - skipping\n")
        continue

    mfes = [t['mfe_r'] for t in trades if t.get('mfe_r') is not None]
    maes = [t['mae_r'] for t in trades if t.get('mae_r') is not None]

    print(f"\n{'-'*60}")
    print(f"  {sym}  |  {len(trades)} trades  |  WR={m['win_rate']*100:.1f}%  "
          f"PF={m['profit_factor'] or 'N/A'}  Net=Rs.{int(m['net_pnl']):+,}")
    print(f"{'-'*60}")

    # Per-trade table
    hdr = f"  {'Date':<12} {'Exit':^12} {'R_mult':>7} {'MFE_r':>7} {'MAE_r':>7}  {'Diagnosis'}"
    print(hdr)
    print(f"  {'-'*75}")
    for t in trades:
        r_mult = t.get('r_multiple', 0) or 0
        mfe    = t.get('mfe_r', 0) or 0
        mae    = t.get('mae_r', 0) or 0
        # Diagnosis
        if mfe < 0.5:
            diag = "[!] entry too late (barely moved)"
        elif mae > 1.0:
            diag = "[!] stop too large (MAE > 1R)"
        elif r_mult >= 1.5:
            diag = "[+] target hit"
        elif r_mult > 0:
            diag = "[~] partial win"
        else:
            diag = "[-] loss"
        entry_dt = t['entry_time'].strftime('%Y-%m-%d') if hasattr(t['entry_time'], 'strftime') else str(t['entry_time'])[:10]
        print(f"  {entry_dt:<12} {t['exit_reason']:^12} {r_mult:>+7.3f} {mfe:>7.3f} {mae:>7.3f}  {diag}")

    # Aggregate diagnostics
    print(f"\n  -- Aggregates ------------------------------------------")
    print(f"  avg_mfe_r          = {m.get('avg_mfe_r', 'n/a')}R")
    print(f"  avg_mae_r          = {m.get('avg_mae_r', 'n/a')}R")
    print(f"  entry_too_late_%   = {m.get('entry_too_late_pct', 'n/a')}%  (MFE < 0.5R)")
    print(f"  stop_too_large_%   = {m.get('stop_too_large_pct', 'n/a')}%  (MAE > 1.0R)")
    print(f"  exit_efficiency_%  = {m.get('exit_efficiency_pct', 'n/a')}%  (R captured / MFE available)")

# Combined MAE/MFE across all symbols
if ALL_TRADES:
    all_mfe = [t['mfe_r'] for t in ALL_TRADES if t.get('mfe_r') is not None]
    all_mae = [t['mae_r'] for t in ALL_TRADES if t.get('mae_r') is not None]
    all_r   = [t['r_multiple'] for t in ALL_TRADES if t.get('r_multiple') is not None]
    print(f"\n{SEP}")
    print(f"  COMBINED ({len(ALL_TRADES)} trades across {BASE_SYMS})")
    print(f"  avg_mfe_r          = {statistics.mean(all_mfe):.3f}R")
    print(f"  avg_mae_r          = {statistics.mean(all_mae):.3f}R")
    print(f"  entry_too_late_%   = {sum(1 for r in all_mfe if r < 0.5)/len(all_mfe)*100:.1f}%")
    print(f"  stop_too_large_%   = {sum(1 for r in all_mae if r > 1.0)/len(all_mae)*100:.1f}%")
    eff = [min(1.0, max(0.0, r/m)) for r,m in zip(all_r, all_mfe) if m > 0]
    print(f"  exit_efficiency_%  = {statistics.mean(eff)*100:.1f}%" if eff else "  exit_efficiency_%  = n/a")
print(SEP)


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 – Universe Test
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'#'*90}")
print("# PART 2: Universe Comparison  [config: best_combo]")
print(f"{'#'*90}\n")

ROW = "  {label:<12} {sym:<11} {t:>5} {wr:>6} {pf:>7} {pnl:>12} {mfe:>8} {mae:>8} {eff:>7}"
HDR = ROW.format(label="UNIVERSE", sym="SYMBOL", t="TRD", wr="WIN%",
                 pf="PF", pnl="NET P&L", mfe="avgMFE_r", mae="avgMAE_r", eff="EXIT%")

for uni_name, syms in [("all10", ALL10), ("momentum5", MOM5), ("banking3", BANK3)]:
    print(f"\n--- Universe: {uni_name} ({len(syms)} symbols) ---")
    print(SEP)
    print(HDR)
    print(SEP)
    pf_vals, pnl_sum, profitable = [], 0, 0
    for sym in syms:
        r, m = run_one(BEST_CFG, sym)
        pf  = m['profit_factor']
        pf_s  = f"{pf:.3f}" if pf else "  N/A"
        pnl_s = ('+' if m['net_pnl'] >= 0 else '') + f"Rs.{int(m['net_pnl']):,}"
        mfe_s = f"{m['avg_mfe_r']:.3f}R" if m.get('avg_mfe_r') else "   n/a"
        mae_s = f"{m['avg_mae_r']:.3f}R" if m.get('avg_mae_r') else "   n/a"
        eff_s = f"{m['exit_efficiency_pct']:.1f}%" if m.get('exit_efficiency_pct') else "   n/a"
        print(ROW.format(label=uni_name, sym=sym, t=m['total_trades'],
                         wr=f"{m['win_rate']*100:.1f}%", pf=pf_s, pnl=pnl_s,
                         mfe=mfe_s, mae=mae_s, eff=eff_s))
        pnl_sum += m['net_pnl']
        if pf: pf_vals.append(pf)
        if m['net_pnl'] > 0: profitable += 1
    print(SEP)
    avg_pf = sum(pf_vals)/len(pf_vals) if pf_vals else 0
    print(f"  Total P&L: {'+' if pnl_sum>=0 else ''}Rs.{int(pnl_sum):,} | "
          f"Avg PF: {avg_pf:.3f} | Profitable: {profitable}/{len(syms)}")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3 – Retest vs Immediate
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'#'*90}")
print("# PART 3: Retest vs Immediate  [base sym: RELIANCE, TCS, HDFCBANK]")
print(f"{'#'*90}\n")
print(SEP)
print(HDR)
print(SEP)

for label, cfg_overrides in [
    ("immediate", {}),
    ("retest_w3_t0.10", dict(entry_mode="retest", retest_window=3, retest_tolerance_pct=0.10)),
    ("retest_w5_t0.10", dict(entry_mode="retest", retest_window=5, retest_tolerance_pct=0.10)),
    ("retest_w5_t0.15", dict(entry_mode="retest", retest_window=5, retest_tolerance_pct=0.15)),
]:
    cfg = {**BEST_CFG, **cfg_overrides}
    for sym in BASE_SYMS:
        r, m = run_one(cfg, sym)
        pf_s  = f"{m['profit_factor']:.3f}" if m['profit_factor'] else "  N/A"
        pnl_s = ('+' if m['net_pnl'] >= 0 else '') + f"Rs.{int(m['net_pnl']):,}"
        mfe_s = f"{m['avg_mfe_r']:.3f}R" if m.get('avg_mfe_r') else "   n/a"
        mae_s = f"{m['avg_mae_r']:.3f}R" if m.get('avg_mae_r') else "   n/a"
        eff_s = f"{m['exit_efficiency_pct']:.1f}%" if m.get('exit_efficiency_pct') else "   n/a"
        print(ROW.format(label=label[:12], sym=sym, t=m['total_trades'],
                         wr=f"{m['win_rate']*100:.1f}%", pf=pf_s, pnl=pnl_s,
                         mfe=mfe_s, mae=mae_s, eff=eff_s))
    print(SEP2)

print(SEP)
print("\nDone. Read diagnosis:")
print("  avg_mfe_r < 0.5  => targets too large, or you're entering too late")
print("  avg_mae_r > 1.0  => stops too large / too tight a channel")
print("  entry_too_late%  => % of trades where the move never materialised at all")
print("  exit_efficiency% => % of available MFE that was actually converted to profit")
