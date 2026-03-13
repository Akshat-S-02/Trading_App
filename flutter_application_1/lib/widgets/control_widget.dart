import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import 'settings_dialog.dart';

class ControlWidget extends StatelessWidget {
  const ControlWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final trading = context.watch<TradingProvider>();

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'CONTROL PANEL',
          style: TextStyle(
            color: Colors.white,
            fontSize: 20,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.2,
          ),
        ),
        const SizedBox(height: 24),
        
        // --- RISK SECTION ---
        _buildSectionTitle('Risk'),
        Card(
          color: Colors.grey[900],
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                _buildProgressBar(
                  'Daily Limit',
                  trading.dailySpent,
                  trading.dailyLimit,
                  Colors.orangeAccent,
                ),
                const SizedBox(height: 16),
                _buildProgressBar(
                  'Monthly Limit',
                  trading.monthlySpent,
                  trading.monthlyLimit,
                  Colors.purpleAccent,
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () {
                      showDialog(
                        context: context,
                        builder: (_) => const SettingsDialog(),
                      );
                    },
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white70,
                      side: const BorderSide(color: Colors.white24),
                    ),
                    child: const Text('Edit Risk Limits'),
                  ),
                ),
              ],
            ),
          ),
        ),
        
        const SizedBox(height: 24),
        // --- STRATEGY SECTION ---
        _buildSectionTitle('Strategy'),
        Card(
          color: Colors.grey[900],
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: const [
                    Text('Momentum ORB v4', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
                    Icon(Icons.settings, color: Colors.white54, size: 20),
                  ],
                ),
                const SizedBox(height: 8),
                const Text('Universe: Momentum5', style: TextStyle(color: Colors.white70)),
                const Text('Trades today: 2', style: TextStyle(color: Colors.white70)),
              ],
            ),
          ),
        ),

        const SizedBox(height: 24),
        // --- AUTOMATION SECTION ---
        _buildSectionTitle('Automation'),
        Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: null, // Placeholder
                icon: const Icon(Icons.play_arrow),
                label: const Text('Start Trading'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.green[800],
                  disabledBackgroundColor: Colors.green[900]?.withOpacity(0.3),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: ElevatedButton.icon(
                onPressed: null, // Placeholder
                icon: const Icon(Icons.pause),
                label: const Text('Pause Trading'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orange[800],
                  disabledBackgroundColor: Colors.orange[900]?.withOpacity(0.3),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              ),
            ),
          ],
        ),

        const SizedBox(height: 32),
        // --- EMERGENCY SECTION ---
        _buildSectionTitle('Emergency'),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: () => _showKillSwitchConfirm(context),
            icon: const Icon(Icons.warning_amber_rounded),
            label: const Text('KILL SWITCH (CANCEL ALL)'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red[800],
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 20),
              textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
          ),
        ),
      ],
    );
  }

  void _showKillSwitchConfirm(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: Colors.redAccent),
            SizedBox(width: 8),
            Text('Are you sure?'),
          ],
        ),
        content: const Text(
          'This will cancel all open orders, close all positions at market price, and halt all automation.\n\nType "KILL" to confirm. (Not implemented yet)',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel', style: TextStyle(color: Colors.white70)),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx), // Placeholder
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red[800], foregroundColor: Colors.white),
            child: const Text('Confirm Kill'),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          color: Colors.indigoAccent[100],
          fontSize: 14,
          fontWeight: FontWeight.bold,
          letterSpacing: 1.1,
        ),
      ),
    );
  }

  Widget _buildProgressBar(
      String label, double spent, double limit, Color color) {
    final progress = limit > 0 ? (spent / limit).clamp(0.0, 1.0) : 0.0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: Colors.white70, fontSize: 14)),
            Text(
              '₹${spent.toStringAsFixed(0)} / ₹${limit.toStringAsFixed(0)}',
              style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold),
            ),
          ],
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: progress,
          backgroundColor: Colors.white12,
          color: color,
          minHeight: 8,
          borderRadius: BorderRadius.circular(4),
        ),
      ],
    );
  }
}
