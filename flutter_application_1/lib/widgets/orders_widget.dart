import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/brutal_theme.dart';
import 'brutal/brutal.dart';

class OrdersWidget extends StatelessWidget {
  const OrdersWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final trades = context.select<TradingProvider, List<dynamic>>((p) => p.trades);

    if (trades.isEmpty) {
      return const BrutalEmpty(
        title: 'No trade history',
        subtitle: 'Executed orders will appear here',
        icon: Icons.receipt_long,
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 8, 20, 24),
      itemCount: trades.length,
      itemBuilder: (context, index) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: TradeRow(trade: trades[index]),
      ),
    );
  }
}

/// One executed trade. Shared by the Orders tab and the terminal order log.
class TradeRow extends StatelessWidget {
  final dynamic trade;
  final bool compact;

  const TradeRow({super.key, required this.trade, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final isBuy = trade['side'] == 'BUY';
    final price = (trade['price'] as num).toDouble();
    final sideColor = isBuy ? Brutal.up : Brutal.down;

    return BrutalBox(
      shadow: compact ? 0 : 3,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              width: compact ? 44 : 54,
              color: sideColor,
              alignment: Alignment.center,
              child: Text(
                isBuy ? 'BUY' : 'SELL',
                style: Brutal.mono(
                    size: compact ? 10 : 12,
                    weight: FontWeight.w900,
                    color: Brutal.white),
              ),
            ),
            Container(width: Brutal.border, color: Brutal.ink),
            Expanded(
              child: Padding(
                padding: EdgeInsets.symmetric(
                    horizontal: 12, vertical: compact ? 8 : 12),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${trade['symbol']}',
                            overflow: TextOverflow.ellipsis,
                            style: Brutal.display(
                                size: compact ? 13 : 15, weight: FontWeight.w800),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            "${trade['created_at']}".split('T')[0], // Simple date formatting
                            style: Brutal.mono(size: 11, color: Brutal.muted),
                          ),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          'QTY ${trade['qty']}',
                          style: Brutal.mono(
                              size: compact ? 12 : 13,
                              weight: FontWeight.w800,
                              color: sideColor),
                        ),
                        Text(
                          '@ ${Brutal.money(price)}',
                          style: Brutal.mono(size: 11, color: Brutal.muted),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
