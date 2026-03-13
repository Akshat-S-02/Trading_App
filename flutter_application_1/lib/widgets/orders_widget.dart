import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class OrdersWidget extends StatelessWidget {
  const OrdersWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final trades = context.select<TradingProvider, List<dynamic>>((p) => p.trades);

    if (trades.isEmpty) {
      return const Center(
        child: Text(
          "No Trade History",
          style: TextStyle(color: Colors.white54, fontSize: 16),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: trades.length,
      itemBuilder: (context, index) {
        final trade = trades[index];
        final isBuy = trade['side'] == 'BUY';
        final price = (trade['price'] as num).toDouble();
        
        final status = trade['status'] as String? ?? 'UNKNOWN';
        final orderId = trade['order_id'] ?? 'N/A';
        final timeStr = trade['created_at'] != null ? trade['created_at'].toString().split('T').last.split('.').first : '--:--:--';
        
        Color statusColor = Colors.grey;
        if (status == 'NEW') statusColor = Colors.blueAccent;
        else if (status == 'FILLED') statusColor = Colors.greenAccent;
        else if (status == 'REJECTED') statusColor = Colors.redAccent;
        else if (status == 'FAILED_RETRYABLE' || status == 'FAILED') statusColor = Colors.orangeAccent;
        
        return Card(
          color: Colors.grey[900],
          margin: const EdgeInsets.only(bottom: 8),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      "${trade['symbol']} ${isBuy ? 'BUY' : 'SELL'}",
                      style: TextStyle(
                        color: isBuy ? Colors.greenAccent : Colors.redAccent,
                        fontWeight: FontWeight.bold,
                        fontSize: 16,
                      ),
                    ),
                    Text(timeStr, style: const TextStyle(color: Colors.white54, fontSize: 12)),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text("Status: $status", style: TextStyle(color: statusColor, fontWeight: FontWeight.bold, fontSize: 13)),
                    Text("Order ID: $orderId", style: const TextStyle(color: Colors.white54, fontSize: 11)),
                  ],
                ),
                const SizedBox(height: 4),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text("Qty: ${trade['qty']}", style: const TextStyle(color: Colors.white70, fontSize: 13)),
                    Text("Avg Price: ₹${price.toStringAsFixed(2)}", style: const TextStyle(color: Colors.white70, fontSize: 13)),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
