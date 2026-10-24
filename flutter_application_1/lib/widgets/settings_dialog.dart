import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/brutal_theme.dart';
import 'brutal/brutal.dart';

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
      showBrutalSnack(context, 'Please enter valid positive limits', isError: true);
      return;
    }

    setState(() => _isLoading = true);
    final success = await context.read<TradingProvider>().setLimits(daily, monthly);

    if (mounted) {
      setState(() => _isLoading = false);
      if (success) {
        showBrutalSnack(context, 'Limits updated successfully');
        Navigator.pop(context);
      } else {
        showBrutalSnack(context, 'Failed to update limits. Check your connection.',
            isError: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      insetPadding: const EdgeInsets.all(20),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 440),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            BrutalStrip(
              index: 'RM',
              title: 'Risk Management',
              actions: [
                if (_isFetching)
                  const SizedBox(
                    width: 14, height: 14,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Brutal.accent),
                  ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('MAX SANDBOX SPEND PER PERIOD', style: Brutal.label()),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _dailyCtrl,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    enabled: !_isFetching,
                    style: Brutal.mono(size: 16, weight: FontWeight.w700),
                    decoration: const InputDecoration(
                      labelText: 'DAILY SPEND LIMIT (₹)',
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _monthlyCtrl,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    enabled: !_isFetching,
                    style: Brutal.mono(size: 16, weight: FontWeight.w700),
                    decoration: const InputDecoration(
                      labelText: 'MONTHLY SPEND LIMIT (₹)',
                    ),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    children: [
                      Expanded(
                        child: BrutalButton(
                          label: 'Cancel',
                          color: Brutal.white,
                          onPressed: () => Navigator.pop(context),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: BrutalButton(
                          label: 'Save',
                          loading: _isLoading,
                          onPressed: (_isLoading || _isFetching) ? null : _save,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
