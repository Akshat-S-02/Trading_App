import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../theme/brutal_theme.dart';
import 'brutal/brutal.dart';

class PortfolioWidget extends StatelessWidget {
  const PortfolioWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final portfolio = context.select<TradingProvider, List<dynamic>>(
        (p) => p.portfolio);

    if (portfolio.isEmpty) {
      return const BrutalEmpty(
        title: 'No holdings',
        subtitle: 'Open the terminal to place a sandbox order',
        icon: Icons.pie_chart_outline,
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 8, 20, 24),
      itemCount: portfolio.length,
      itemBuilder: (context, index) =>
          PortfolioItem(item: portfolio[index]),
    );
  }
}

class PortfolioItem extends StatelessWidget {
  final dynamic item;
  final bool compact;
  final VoidCallback? onTap;

  const PortfolioItem({
    super.key,
    required this.item,
    this.compact = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final symbol   = item['symbol'] as String;
    final qty      = item['qty'].toString();
    final avgPrice = (item['avg_price'] as num).toDouble();

    // Live price comes from MarketDataProvider; fall back to avg price.
    final livePrice = context.select<MarketDataProvider, double?>(
          (p) => p.getPrice(symbol)) ?? avgPrice;

    final currentValue = livePrice * (item['qty'] as num);
    final investValue  = avgPrice  * (item['qty'] as num);
    final pnl          = currentValue - investValue;
    final pnlPercent   = investValue == 0
        ? 0.0
        : (pnl / investValue) * 100;
    final pnlColor = Brutal.signColor(pnl);

    return Padding(
      padding: EdgeInsets.only(bottom: compact ? 8 : 12),
      child: InkWell(
        onTap: onTap,
        child: BrutalBox(
          shadow: compact ? 0 : 3,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(symbol,
                          overflow: TextOverflow.ellipsis,
                          style: Brutal.display(
                              size: compact ? 14 : 17, weight: FontWeight.w800)),
                    ),
                    BrutalTag('Qty $qty', color: Brutal.accent),
                  ],
                ),
              ),
              Container(height: Brutal.border, color: Brutal.ink),
              IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _cell('Invested', Brutal.money(investValue)),
                    Container(width: 1.5, color: Brutal.ink),
                    _cell('Current', Brutal.money(currentValue)),
                    Container(width: 1.5, color: Brutal.ink),
                    _cell(
                      'P&L',
                      '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)}'
                          ' (${pnlPercent.toStringAsFixed(2)}%)',
                      color: pnlColor,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _cell(String label, String value, {Color color = Brutal.ink}) {
    return Expanded(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label.toUpperCase(), style: Brutal.label(size: 10)),
            const SizedBox(height: 3),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(value,
                  style: Brutal.mono(
                      size: compact ? 12 : 13,
                      weight: FontWeight.w800,
                      color: color)),
            ),
          ],
        ),
      ),
    );
  }
}
