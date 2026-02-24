import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class LtpWidget extends StatelessWidget {
  final String symbol;
  final VoidCallback? onRemove;

  const LtpWidget({super.key, required this.symbol, this.onRemove});

  /// Strips exchange suffix for clean display (e.g. "ULTRACEMCO.NS" → "ULTRACEMCO")
  String _displayName(String sym) {
    if (sym.contains('.')) return sym.split('.').first;
    return sym;
  }

  @override
  Widget build(BuildContext context) {
    final price = context.select<TradingProvider, double?>(
      (p) => p.getPrice(symbol),
    );

    final displaySymbol = _displayName(symbol);

    return Card(
      elevation: 2,
      color: Colors.grey[900],
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            // Left: Symbol name + exchange label — flex to avoid overflow
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    displaySymbol,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 1,
                  ),
                  Text(
                    "NSE",
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.white.withOpacity(0.5),
                    ),
                  ),
                ],
              ),
            ),

            // Right: Price + Delete button — fixed, no overflow
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                price != null
                    ? Text(
                        "₹${price.toStringAsFixed(2)}",
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: Colors.greenAccent,
                        ),
                      )
                    : const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                if (onRemove != null) ...[
                  const SizedBox(width: 8),
                  IconButton(
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    icon: const Icon(Icons.delete, color: Colors.red, size: 20),
                    onPressed: onRemove,
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}
