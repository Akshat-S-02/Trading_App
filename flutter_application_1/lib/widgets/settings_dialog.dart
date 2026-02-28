import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class SettingsDialog extends StatefulWidget {
  const SettingsDialog({super.key});

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  final _dailyCtrl = TextEditingController();
  final _monthlyCtrl = TextEditingController();
  bool _isLoading = false;
  bool _isFetching = true; // true while we load fresh limits from the server

  @override
  void initState() {
    super.initState();
    // Populate immediately with whatever the provider already holds
    // (may be 0 if not yet fetched), then re-fetch to get the latest values.
    _syncFromProvider();
    _refreshLimits();
  }

  void _syncFromProvider() {
    final provider = context.read<TradingProvider>();
    _dailyCtrl.text   = _fmt(provider.dailyLimit);
    _monthlyCtrl.text = _fmt(provider.monthlyLimit);
  }

  /// Pull fresh limits from the server then repopulate the text fields.
  Future<void> _refreshLimits() async {
    setState(() => _isFetching = true);
    await context.read<TradingProvider>().fetchUserLimits();
    if (!mounted) return;
    _syncFromProvider();
    setState(() => _isFetching = false);
  }

  /// Format a double without unnecessary trailing zeros (e.g. 5000.0 → "5000")
  String _fmt(double v) => v == v.truncateToDouble() ? v.toInt().toString() : v.toString();

  @override
  void dispose() {
    _dailyCtrl.dispose();
    _monthlyCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final daily   = double.tryParse(_dailyCtrl.text.trim())   ?? 0;
    final monthly = double.tryParse(_monthlyCtrl.text.trim()) ?? 0;

    if (daily <= 0 || monthly <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter valid positive limits')),
      );
      return;
    }

    setState(() => _isLoading = true);
    final success = await context.read<TradingProvider>().setLimits(daily, monthly);

    if (mounted) {
      setState(() => _isLoading = false);
      if (success) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('✅ Limits updated successfully')),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('❌ Failed to update limits. Check your connection.'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: [
          const Expanded(
            child: Text('Risk Management Settings'),
          ),
          if (_isFetching) ...[
            const SizedBox(width: 10),
            const SizedBox(
              width: 16, height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ],
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _dailyCtrl,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            enabled: !_isFetching,
            decoration: const InputDecoration(
              labelText: 'Daily Spend Limit (₹)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _monthlyCtrl,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            enabled: !_isFetching,
            decoration: const InputDecoration(
              labelText: 'Monthly Spend Limit (₹)',
              border: OutlineInputBorder(),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: (_isLoading || _isFetching) ? null : _save,
          child: _isLoading
              ? const SizedBox(
                  width: 20, height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('Save'),
        ),
      ],
    );
  }
}
