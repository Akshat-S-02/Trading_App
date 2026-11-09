import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../utils/format.dart';
import '../screens/chart_screen.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

/// Positions tab: day summary, open positions with live P&L and one-tap
/// close / edit SL-target, and orders still waiting to fill.
class PortfolioWidget extends StatelessWidget {
  const PortfolioWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final trading = context.watch<TradingProvider>();
    final market = context.watch<MarketDataProvider>();
    final positions = trading.positions;
    final pending = trading.pendingOrders;

    double openPnl = 0;
    for (final p in positions) {
      final pnl = _livePnl(p, market);
      if (pnl != null) openPnl += pnl;
    }

    final m = trading.portfolioMetrics;
    final realized = (m['realized_pnl'] ?? 0).toDouble();
    final today = (m['gross_pnl_today'] ?? 0).toDouble();
    final winRate = (m['win_rate'] ?? 0).toDouble();
    final tradesToday = m['total_trades_today'] ?? 0;
    final wins = m['winning_trades_today'] ?? 0;
    final losses = m['losing_trades_today'] ?? 0;

    return RefreshIndicator(
      onRefresh: trading.refreshAll,
      child: ListView(
        padding: EdgeInsets.fromLTRB(16, 8, 16, bottomInset(context)),
        children: [
          // ── Summary: the one number that matters is the biggest thing here.
          Surface(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Open P&L', style: AppText.footnote),
                const SizedBox(height: 2),
                Text(signedInr(openPnl),
                    style: AppText.largeTitle.copyWith(color: pnlColor(openPnl), fontFeatures: AppText.tabular)),
                const SizedBox(height: 2),
                Text('${positions.length} open position${positions.length == 1 ? '' : 's'}',
                    style: AppText.footnote),
                const SizedBox(height: 16),
                const Divider(),
                const SizedBox(height: 12),
                Row(
                  children: [
                    _stat('Today', signedInr(today), pnlColor(today)),
                    _stat('All-time', signedInr(realized), pnlColor(realized)),
                    _stat('Win rate', '${winRate.toStringAsFixed(0)}%', AppColors.label),
                    _stat('Trades', '$tradesToday · ${wins}W ${losses}L', AppColors.label),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          // ── Open positions ───────────────────────────────────────────────
          const SectionHeader('Open positions'),
          if (positions.isEmpty)
            const EmptyState(
              icon: Icons.inbox_outlined,
              title: 'No open positions',
              message: 'Place a trade from the Market tab, or turn on auto-trading.',
            )
          else
            ...positions.map((p) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _PositionCard(position: p),
                )),

          // ── Pending orders ───────────────────────────────────────────────
          if (pending.isNotEmpty) ...[
            const SizedBox(height: 12),
            const SectionHeader('Waiting to fill'),
            InsetGroup(
              dividerIndent: 54,
              children: pending.map((o) {
                final buy = o['side'] == 'BUY';
                return ListTile(
                  leading: const SizedBox(
                      width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2)),
                  title: Text('${buy ? 'Buy' : 'Sell'} ${o['qty']} × ${o['symbol']}',
                      style: AppText.headline.copyWith(color: buy ? kBuyColor : kSellColor)),
                  subtitle: Text(
                      '${o['status']} · ${o['source'] == 'manual' ? 'Manual' : 'Auto'} · ${timeOf(o['created_at'])}'),
                  trailing: o['status'] == 'NEW'
                      ? const Tooltip(
                          message: 'Orders fill when the outbox worker is running',
                          child: Icon(Icons.info_outline_rounded, color: AppColors.tertiary))
                      : null,
                );
              }).toList(),
            ),
          ],
        ],
      ),
    );
  }

  static double? _livePnl(Map<String, dynamic> p, MarketDataProvider market) {
    final ltp = market.getPrice(p['symbol']) ?? (p['ltp'] as num?)?.toDouble();
    final avg = ((p['avg_price'] ?? p['entry_price']) as num?)?.toDouble();
    if (ltp == null || avg == null) return (p['unrealized_pnl'] as num?)?.toDouble();
    final qty = (p['filled_qty'] ?? p['qty']) as int;
    return (p['side'] == 'BUY' ? ltp - avg : avg - ltp) * qty;
  }

  Widget _stat(String label, String value, Color color) => Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: AppText.caption),
            const SizedBox(height: 2),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(value,
                  style: AppText.subhead.copyWith(color: color, fontFeatures: AppText.tabular)),
            ),
          ],
        ),
      );
}

class _PositionCard extends StatelessWidget {
  final Map<String, dynamic> position;
  const _PositionCard({required this.position});

  @override
  Widget build(BuildContext context) {
    final p = position;
    final id = p['id'] as int;
    final market = context.watch<MarketDataProvider>();
    final trading = context.watch<TradingProvider>();
    final isLong = p['side'] == 'BUY';
    final qty = (p['filled_qty'] ?? p['qty']) as int;
    final avg = ((p['avg_price'] ?? p['entry_price']) as num?)?.toDouble() ?? 0;
    final ltp = market.getPrice(p['symbol']) ?? (p['ltp'] as num?)?.toDouble();
    final pnl = PortfolioWidget._livePnl(p, market);
    final pnlPct = (pnl != null && avg > 0) ? pnl / (avg * qty) * 100 : null;
    final sl = (p['stop_loss'] as num?)?.toDouble();
    final tgt = (p['target'] as num?)?.toDouble();
    final isManual = p['source'] == 'manual';
    final closing = trading.isClosing(id);

    final sideColor = isLong ? kBuyColor : kSellColor;

    return Surface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              // Left group takes the free space; symbol/tag only shorten when it runs out.
              Expanded(
                child: Row(
                  children: [
                    Pill(isLong ? 'Long' : 'Short', color: sideColor),
                    const SizedBox(width: 8),
                    Flexible(
                      flex: 3,
                      child: Text(p['symbol'],
                          maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.title3),
                    ),
                    const SizedBox(width: 8),
                    Flexible(
                      flex: 2,
                      child: Pill(
                          isManual ? 'Manual' : _strategyLabel(p['strategy_name']),
                          color: AppColors.secondary),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(signedInr(pnl),
                      style: AppText.headline.copyWith(color: pnlColor(pnl), fontFeatures: AppText.tabular)),
                  if (pnlPct != null)
                    Text('${pnlPct >= 0 ? '+' : ''}${pnlPct.toStringAsFixed(2)}%',
                        style: AppText.footnote.copyWith(color: pnlColor(pnl), fontFeatures: AppText.tabular)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _kv('Qty', '$qty'),
              _kv('Avg', inr(avg)),
              _kv('LTP', inr(ltp)),
            ],
          ),
          const SizedBox(height: 14),
          _bracketBar(context, isLong, avg, ltp, sl, tgt),
          const SizedBox(height: 10),
          Text('Opened ${timeOf(p['created_at'])}', style: AppText.caption),
          const SizedBox(height: 12),
          // Buttons share the width so the row can never overflow on narrow phones.
          Row(
            children: [
              IconButton.filledTonal(
                tooltip: 'Chart',
                style: IconButton.styleFrom(backgroundColor: AppColors.fill),
                onPressed: () => openChart(context, p['symbol']),
                icon: const Icon(Icons.show_chart_rounded, size: 20),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton(
                  onPressed: () => _editBracket(context, p, ltp ?? avg),
                  child: const FittedBox(child: Text('SL / Target')),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: AppColors.red.withValues(alpha: 0.18), foregroundColor: AppColors.red),
                  onPressed: closing ? null : () => _confirmClose(context, p, pnl),
                  child: closing
                      ? const SizedBox(
                          width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.red))
                      : const Text('Close'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  static String _strategyLabel(dynamic name) {
    final s = (name ?? 'auto').toString().replaceAll('_', ' ');
    return s.isEmpty ? 'Auto' : '${s[0].toUpperCase()}${s.substring(1)}';
  }

  /// Where the price sits between stop-loss and target. The marker eases to
  /// each new price rather than jumping.
  Widget _bracketBar(BuildContext context, bool isLong, double avg, double? ltp, double? sl, double? tgt) {
    if (sl == null && tgt == null) {
      return Row(
        children: [
          const Icon(Icons.warning_amber_rounded, size: 16, color: AppColors.orange),
          const SizedBox(width: 6),
          Expanded(
            child: Text('No stop-loss or target. Exits only at the 15:20 square-off or when you close it.',
                style: AppText.footnote.copyWith(color: AppColors.orange)),
          ),
        ],
      );
    }
    double? progress;
    if (sl != null && tgt != null && ltp != null && tgt != sl) {
      progress = ((ltp - sl) / (tgt - sl)).clamp(0.0, 1.0);
    }
    return Column(
      children: [
        if (progress != null)
          TweenAnimationBuilder<double>(
            tween: Tween(end: progress),
            duration: motionDuration(context, 400),
            curve: motionCurve,
            builder: (_, v, __) => SizedBox(
              height: 6,
              child: LayoutBuilder(
                builder: (_, c) => Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Container(
                      decoration: const ShapeDecoration(
                        shape: StadiumBorder(),
                        gradient: LinearGradient(colors: [Color(0x66FF453A), Color(0x6630D158)]),
                      ),
                    ),
                    Positioned(
                      left: (c.maxWidth * v - 6).clamp(-2.0, c.maxWidth - 10),
                      top: -3,
                      child: Container(
                        width: 12,
                        height: 12,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: Colors.white,
                          boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.4), blurRadius: 4)],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        if (progress != null) const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Flexible(
              child: Text('SL ${sl == null ? '—' : inr(sl)}',
                  overflow: TextOverflow.ellipsis,
                  style: AppText.footnote.copyWith(color: kSellColor, fontFeatures: AppText.tabular)),
            ),
            const SizedBox(width: 8),
            Flexible(
              child: Text('Target ${tgt == null ? '—' : inr(tgt)}',
                  overflow: TextOverflow.ellipsis,
                  style: AppText.footnote.copyWith(color: kBuyColor, fontFeatures: AppText.tabular)),
            ),
          ],
        ),
      ],
    );
  }

  Widget _kv(String k, String v) => Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(k, style: AppText.caption),
            const SizedBox(height: 2),
            Text(v, style: AppText.subhead.copyWith(fontFeatures: AppText.tabular)),
          ],
        ),
      );

  Future<void> _confirmClose(BuildContext context, Map<String, dynamic> p, double? pnl) async {
    final trading = context.read<TradingProvider>();
    final messenger = ScaffoldMessenger.of(context);
    final ok = await confirmAction(
      context,
      title: 'Close ${p['symbol']}?',
      message: 'Squares off ${p['filled_qty'] ?? p['qty']} shares at market.\n'
          'Estimated P&L ${signedInr(pnl)}, before charges.',
      confirmLabel: 'Close position',
      cancelLabel: 'Keep open',
    );
    if (!ok) return;
    final res = await trading.closePosition(p['id'] as int);
    notify(messenger, res.message, ok: res.ok);
  }

  Future<void> _editBracket(BuildContext context, Map<String, dynamic> p, double ref) async {
    final trading = context.read<TradingProvider>();
    final messenger = ScaffoldMessenger.of(context);
    final slCtrl = TextEditingController(text: (p['stop_loss'] as num?)?.toStringAsFixed(2) ?? '');
    final tgtCtrl = TextEditingController(text: (p['target'] as num?)?.toStringAsFixed(2) ?? '');
    final isLong = p['side'] == 'BUY';

    final saved = await showAppSheet<bool>(
      context,
      (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.viewInsetsOf(ctx).bottom + 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${p['symbol']} stop-loss & target', style: AppText.title2),
            const SizedBox(height: 4),
            Text('Price now ${inr(ref)}. '
                '${isLong ? 'Stop-loss goes below, target above.' : 'Stop-loss goes above, target below.'} '
                'Leave a field empty to remove it.',
                style: AppText.footnote),
            const SizedBox(height: 20),
            TextField(
              controller: slCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
              decoration: const InputDecoration(labelText: 'Stop-loss', prefixText: '₹ '),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: tgtCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
              decoration: const InputDecoration(labelText: 'Target', prefixText: '₹ '),
            ),
            const SizedBox(height: 20),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
          ],
        ),
      ),
    );
    if (saved != true) return;
    final sl = double.tryParse(slCtrl.text), tgt = double.tryParse(tgtCtrl.text);
    // A typo must not read as "empty", which would remove the stop.
    if ((slCtrl.text.isNotEmpty && sl == null) || (tgtCtrl.text.isNotEmpty && tgt == null)) {
      notify(messenger, 'Not saved: stop-loss or target is not a valid number.', ok: false);
      return;
    }
    final res = await trading.updateBracket(p['id'] as int, stopLoss: sl, target: tgt);
    notify(messenger, res.message, ok: res.ok);
  }
}
