import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_data_provider.dart';
import '../theme/brutal_theme.dart';
import 'brutal/brutal.dart';

class LtpWidget extends StatelessWidget {
  final String symbol;
  final VoidCallback? onRemove;

  const LtpWidget({super.key, required this.symbol, this.onRemove});

  /// Strips exchange suffix for clean display (e.g. "ULTRACEMCO.NS" → "ULTRACEMCO")
  String _displayName(String sym) =>
      sym.contains('.') ? sym.split('.').first : sym;

  @override
  Widget build(BuildContext context) {
    final price = context.select<MarketDataProvider, double?>(
      (p) => p.getPrice(symbol),
    );
    final change = context.select<MarketDataProvider, double?>(
      (p) => p.sessionChange(symbol),
    );

    final displaySymbol = _displayName(symbol);

    return BrutalBox(
      shadow: 3,
      padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
      child: Row(
        children: [
          // Left: symbol name + exchange label
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  displaySymbol,
                  style: Brutal.display(size: 17, weight: FontWeight.w800),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                ),
                const SizedBox(height: 4),
                const BrutalTag('NSE'),
              ],
            ),
          ),

          // Right: price + optional delete button
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              price != null
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          Brutal.money(price),
                          style: Brutal.mono(size: 16, weight: FontWeight.w800),
                        ),
                        if (change != null && change != 0)
                          Text(
                            '${change > 0 ? '▲' : '▼'} ${change.abs().toStringAsFixed(2)}',
                            style: Brutal.mono(
                                size: 11,
                                weight: FontWeight.w700,
                                color: Brutal.signColor(change)),
                          ),
                      ],
                    )
                  : const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    ),
              if (onRemove != null) ...[
                const SizedBox(width: 8),
                IconButton(
                  tooltip: 'Remove $displaySymbol',
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.close, color: Brutal.ink, size: 20),
                  onPressed: onRemove,
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}
