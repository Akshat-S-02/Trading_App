import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../utils/format.dart';
import 'order_ticket_sheet.dart';
import '../ui/components.dart';
import '../ui/theme.dart';
import '../screens/chart_screen.dart';

/// Watchlist row: live price that flashes green/red on each change, a badge
/// when you hold a position, and one-tap BUY / SELL.
class LtpWidget extends StatefulWidget {
  final String symbol;
  const LtpWidget({super.key, required this.symbol});

  @override
  State<LtpWidget> createState() => _LtpWidgetState();
}

class _LtpWidgetState extends State<LtpWidget> {
  double? _lastPrice;
  int _direction = 0; // 1 up, -1 down, 0 unchanged

  @override
  Widget build(BuildContext context) {
    final price = context.select<MarketDataProvider, double?>(
      (p) => p.getPrice(widget.symbol),
    );
    if (price != null && _lastPrice != null && price != _lastPrice) {
      _direction = price > _lastPrice! ? 1 : -1;
    }
    _lastPrice = price;

    final display = bareSymbol(widget.symbol);
    final heldQty = context.select<TradingProvider, int>((t) => t.positions
        .where((p) => p['symbol'] == display)
        .fold<int>(0, (sum, p) {
          final q = (p['filled_qty'] ?? p['qty']) as int;
          return sum + (p['side'] == 'BUY' ? q : -q);
        }));

    final flashColor = _direction > 0
        ? kBuyColor
        : _direction < 0
            ? kSellColor
            : AppColors.label;

    return Pressable(
      onTap: () => openChart(context, widget.symbol),
      child: Surface(
        padding: const EdgeInsets.fromLTRB(16, 12, 10, 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(display,
                            maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.headline),
                      ),
                      if (heldQty != 0) ...[
                        const SizedBox(width: 8),
                        Pill(heldQty > 0 ? 'Long $heldQty' : 'Short ${heldQty.abs()}',
                            color: heldQty > 0 ? kBuyColor : kSellColor),
                      ],
                    ],
                  ),
                  const SizedBox(height: 2),
                  const Text('NSE', style: AppText.caption),
                ],
              ),
            ),
            // The price flashes the direction of the last tick, then settles.
            TweenAnimationBuilder<Color?>(
              key: ValueKey(price),
              tween: ColorTween(begin: flashColor, end: AppColors.label),
              duration: const Duration(milliseconds: 900),
              curve: Curves.easeOut,
              builder: (_, color, __) => Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_direction != 0)
                    Icon(_direction > 0 ? Icons.arrow_drop_up_rounded : Icons.arrow_drop_down_rounded,
                        color: color, size: 22),
                  Text(
                    price == null ? '—' : inr(price),
                    style: AppText.headline.copyWith(color: color, fontFeatures: AppText.tabular),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            _quickButton(context, 'B', kBuyColor, 'BUY'),
            const SizedBox(width: 6),
            _quickButton(context, 'S', kSellColor, 'SELL'),
          ],
        ),
      ),
    );
  }

  Widget _quickButton(BuildContext context, String label, Color color, String side) {
    return Semantics(
      button: true,
      label: side == 'BUY' ? 'Buy' : 'Sell',
      child: Pressable(
        pressedScale: 0.9,
        haptic: true,
        onTap: () => showOrderTicket(context, widget.symbol, side: side),
        child: Container(
          width: 36,
          height: 36,
          alignment: Alignment.center,
          decoration: ShapeDecoration(color: color.withValues(alpha: 0.18), shape: rounded(10)),
          child: Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 15)),
        ),
      ),
    );
  }
}
