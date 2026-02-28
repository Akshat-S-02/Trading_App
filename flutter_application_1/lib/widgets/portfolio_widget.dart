import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';

class PortfolioWidget extends StatelessWidget {
  const PortfolioWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final portfolio = context.select<TradingProvider, List<dynamic>>(
        (p) => p.portfolio);

    if (portfolio.isEmpty) {
      return const Center(
        child: Text(
          'No Holdings',
          style: TextStyle(color: Colors.white54, fontSize: 16),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: portfolio.length,
      itemBuilder: (context, index) =>
          PortfolioItem(item: portfolio[index]),
    );
  }
}

class PortfolioItem extends StatelessWidget {
  final dynamic item;

  const PortfolioItem({super.key, required this.item});

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

    return Card(
      color: const Color(0xFF212121),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(symbol,
                    style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: Colors.white)),
                Text('Qty: $qty',
                    style: const TextStyle(color: Colors.white70)),
              ],
            ),
            const Divider(color: Colors.white24),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Invested',
                        style: TextStyle(color: Colors.white54, fontSize: 12)),
                    Text('₹${investValue.toStringAsFixed(2)}',
                        style: const TextStyle(color: Colors.white)),
                  ],
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Text('Current',
                        style: TextStyle(color: Colors.white54, fontSize: 12)),
                    Text('₹${currentValue.toStringAsFixed(2)}',
                        style: const TextStyle(color: Colors.white)),
                  ],
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Text('P&L',
                        style: TextStyle(color: Colors.white54, fontSize: 12)),
                    Text(
                      '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)}'
                      ' (${pnlPercent.toStringAsFixed(2)}%)',
                      style: TextStyle(
                        color: pnl >= 0 ? Colors.greenAccent : Colors.redAccent,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
