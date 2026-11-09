import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../utils/format.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

/// Order history with All / Manual / Auto filter.
class OrdersWidget extends StatefulWidget {
  const OrdersWidget({super.key});

  @override
  State<OrdersWidget> createState() => _OrdersWidgetState();
}

class _OrdersWidgetState extends State<OrdersWidget> {
  String _filter = 'all';

  @override
  Widget build(BuildContext context) {
    final trading = context.watch<TradingProvider>();
    final trades = trading.trades
        .where((t) => _filter == 'all' || t['source'] == _filter)
        .toList();

    final closed = trades.where((t) => t['status'] == 'CLOSED');
    final net = closed.fold<double>(0, (s, t) => s + ((t['pnl'] ?? 0) as num).toDouble());

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Row(
            children: [
              Expanded(
                child: SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'all', label: Text('All')),
                    ButtonSegment(value: 'manual', label: Text('Manual')),
                    ButtonSegment(value: 'auto', label: Text('Auto')),
                  ],
                  selected: {_filter},
                  onSelectionChanged: (s) {
                    HapticFeedback.selectionClick();
                    setState(() => _filter = s.first);
                  },
                  showSelectedIcon: false,
                ),
              ),
              const SizedBox(width: 16),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Text('Closed P&L', style: AppText.caption),
                  Text(signedInr(net),
                      style: AppText.headline.copyWith(color: pnlColor(net), fontFeatures: AppText.tabular)),
                ],
              ),
            ],
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: trading.fetchTrades,
            child: trades.isEmpty
                ? ListView(children: const [
                    SizedBox(height: 60),
                    EmptyState(
                      icon: Icons.receipt_long_outlined,
                      title: 'No orders yet',
                      message: 'Orders you place, and ones auto-trading places, show up here.',
                    ),
                  ])
                : ListView.separated(
                    padding: EdgeInsets.fromLTRB(16, 8, 16, bottomInset(context)),
                    itemCount: trades.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (context, i) => _OrderTile(trade: trades[i]),
                  ),
          ),
        ),
      ],
    );
  }
}

class _OrderTile extends StatelessWidget {
  final dynamic trade;
  const _OrderTile({required this.trade});

  static Color _statusColor(String s) {
    switch (s) {
      case 'CLOSED':
        return AppColors.secondary;
      case 'FILLED':
        return AppColors.green;
      case 'REJECTED':
      case 'FAILED_FATAL':
        return AppColors.red;
      case 'FAILED_RETRYABLE':
        return AppColors.orange;
      default:
        return AppColors.teal;
    }
  }

  static String _statusLabel(String s) {
    switch (s) {
      case 'FILLED':
        return 'Open';
      case 'NEW':
      case 'ENQUEUED':
      case 'SENDING':
        return 'Pending';
      default:
        final w = s.replaceAll('_', ' ').toLowerCase();
        return w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}';
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = trade;
    final isBuy = t['side'] == 'BUY';
    final status = (t['status'] ?? 'UNKNOWN').toString();
    final price = (t['price'] as num?)?.toDouble();
    final exit = (t['exit_price'] as num?)?.toDouble();
    final pnl = (t['pnl'] as num?)?.toDouble();
    final isManual = t['source'] == 'manual';
    final strategy = (t['strategy_name'] ?? 'auto').toString();

    final sideColor = isBuy ? kBuyColor : kSellColor;

    return Surface(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 28,
                height: 28,
                alignment: Alignment.center,
                decoration: ShapeDecoration(color: sideColor.withValues(alpha: 0.16), shape: rounded(8)),
                child: Icon(isBuy ? Icons.north_east_rounded : Icons.south_east_rounded, size: 16, color: sideColor),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text('${isBuy ? 'Buy' : 'Sell'} ${t['qty']} × ${t['symbol']}',
                    maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.headline),
              ),
              Pill(_statusLabel(status), color: _statusColor(status)),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: Text(
                  exit != null ? '${inr(price)} → ${inr(exit)}' : 'Entry ${inr(price)}',
                  style: AppText.callout.copyWith(color: AppColors.secondary, fontFeatures: AppText.tabular),
                ),
              ),
              if (status == 'CLOSED')
                Text(signedInr(pnl),
                    style: AppText.headline.copyWith(color: pnlColor(pnl), fontFeatures: AppText.tabular)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            [
              isManual ? 'Manual' : 'Auto · $strategy',
              if (t['exit_reason'] != null) 'exit ${t['exit_reason']}',
              timeOf(t['created_at']),
            ].join(' · '),
            style: AppText.caption,
          ),
        ],
      ),
    );
  }
}
