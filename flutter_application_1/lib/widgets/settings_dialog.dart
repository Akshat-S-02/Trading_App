import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

/// Opens the risk-limit editor as a sheet.
Future<void> showRiskLimits(BuildContext context) =>
    showAppSheet(context, (_) => const SettingsDialog());

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
  String? _error;

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

    // Validate inline, next to the fields, instead of after a round trip.
    if (daily <= 0 || monthly <= 0) {
      HapticFeedback.heavyImpact();
      setState(() => _error = 'Both limits must be more than ₹0.');
      return;
    }
    if (daily > monthly) {
      HapticFeedback.heavyImpact();
      setState(() => _error = 'The daily limit can’t be higher than the monthly limit.');
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
    });
    final messenger = ScaffoldMessenger.of(context);
    final success = await context.read<TradingProvider>().setLimits(daily, monthly);

    if (!mounted) return;
    setState(() => _isLoading = false);
    if (success) {
      Navigator.pop(context);
      notify(messenger, 'Risk limits updated');
    } else {
      HapticFeedback.heavyImpact();
      setState(() => _error = 'Couldn’t save. Check the connection to the backend and try again.');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.viewInsetsOf(context).bottom + 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Expanded(child: Text('Risk limits', style: AppText.title2)),
              if (_isFetching)
                const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
            ],
          ),
          const SizedBox(height: 4),
          const Text('The most new trades can spend. Orders past a limit are blocked.',
              style: AppText.footnote),
          const SizedBox(height: 20),
          _field(_dailyCtrl, 'Daily limit'),
          const SizedBox(height: 12),
          _field(_monthlyCtrl, 'Monthly limit'),
          AnimatedSize(
            duration: motionDuration(context, 220),
            curve: motionCurve,
            alignment: Alignment.topCenter,
            child: _error == null
                ? const SizedBox(width: double.infinity)
                : Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Text(_error!, style: AppText.footnote.copyWith(color: AppColors.red)),
                  ),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: (_isLoading || _isFetching) ? null : _save,
            child: _isLoading
                ? const SizedBox(
                    width: 20, height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Text('Save'),
          ),
        ],
      ),
    );
  }

  Widget _field(TextEditingController c, String label) => TextField(
        controller: c,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
        enabled: !_isFetching,
        style: AppText.body.copyWith(fontFeatures: AppText.tabular),
        onChanged: (_) {
          if (_error != null) setState(() => _error = null);
        },
        decoration: InputDecoration(labelText: label, prefixText: '₹ '),
      );
}
