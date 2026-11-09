import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart' show NumberFormat;
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../utils/format.dart';
import 'settings_dialog.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

// ── Per-strategy display metadata ─────────────────────────────────────────────
const Map<String, Map<String, Object>> _strategyMeta = {
  'orb_v4': {
    'icon': Icons.rocket_launch_outlined,
    'type': 'Breakout',
    'regime': 'High Vol · Trending',
    'accentColor': AppColors.teal,
    'description':
        'Opening Range Breakout v4. Fires on the first 5-min candle that '
        'breaks the opening range with momentum confirmation.',
  },
  'ema_momentum': {
    'icon': Icons.trending_up,
    'type': 'Momentum',
    'regime': 'Low Vol · Trending',
    'accentColor': AppColors.green,
    'description':
        'EMA crossover (9/21) with ADX filter. Captures sustained intraday '
        'momentum in low-volatility trending sessions.',
  },
  'vwap_reversion': {
    'icon': Icons.sync_alt,
    'type': 'Mean-Reversion',
    'regime': 'High Vol · Ranging',
    'accentColor': AppColors.orange,
    'description':
        'Fades extreme deviations from VWAP. Enters when price is stretched '
        '>1.5σ from VWAP and RSI shows oversold/overbought exhaustion.',
  },
  'supertrend': {
    'icon': Icons.show_chart,
    'type': 'Trend-Following',
    'regime': 'Low Vol · Ranging',
    'accentColor': AppColors.purple,
    'description':
        'ATR-based Supertrend (period=10, mult=3). Rides directional moves '
        'in low-volatility conditions and flips on band crossovers.',
  },
};

const Map<String, Object> _defaultMeta = {
  'icon': Icons.auto_awesome,
  'type': 'Strategy',
  'regime': 'All Regimes',
  'accentColor': AppColors.accent,
  'description': 'Routed by the Decision Engine based on current market regime.',
};

// ─────────────────────────────────────────────────────────────────────────────

class ControlWidget extends StatelessWidget {
  const ControlWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final trading = context.watch<TradingProvider>();

    final regimes = trading.paperStatus['current_regime'] as Map?;

    return ListView(
      padding: EdgeInsets.fromLTRB(16, 8, 16, bottomInset(context)),
      children: [
        if (trading.emergencyStop) _buildEmergencyBanner(context),
        _buildAutomationCard(context, trading),
        const SizedBox(height: 28),

        // ── Risk ────────────────────────────────────────────────────────────
        SectionHeader('Risk',
            trailing: TextButton(onPressed: () => showRiskLimits(context), child: const Text('Edit'))),
        Surface(
          child: Column(
            children: [
              _buildProgressBar(context, 'Daily', trading.dailySpent, trading.dailyLimit),
              const SizedBox(height: 18),
              _buildProgressBar(context, 'Monthly', trading.monthlySpent, trading.monthlyLimit),
            ],
          ),
        ),

        const SizedBox(height: 28),

        // ── Strategies ──────────────────────────────────────────────────────
        const SectionHeader('Strategies'),
        if (trading.paperStatus.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Center(child: CircularProgressIndicator()),
          )
        else ...[
          if (regimes != null && regimes.isNotEmpty) ...[
            InsetGroup(
              children: regimes.entries.take(3).map((e) {
                final up = e.value.toString().contains('UPTREND');
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: Row(
                    children: [
                      Expanded(child: Text(e.key.toString(), style: AppText.callout)),
                      Pill(_title(e.value.toString()),
                          color: up ? AppColors.green : AppColors.orange,
                          icon: up ? Icons.trending_up_rounded : Icons.trending_down_rounded),
                    ],
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 4),
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 4, 16, 12),
              child: Text('Market regime per stock. It decides which strategy gets to trade.',
                  style: AppText.caption),
            ),
          ],

          // Strategy cards — fully dynamic, driven by backend weights map
          if (trading.paperStatus['strategy_weights'] != null)
            ...(trading.paperStatus['strategy_weights'] as Map)
                .entries
                .map((e) => _buildStrategyCard(e.key.toString(), e.value)),
        ],

        const SizedBox(height: 28),

        // ── Emergency ───────────────────────────────────────────────────────
        const SectionHeader('Emergency'),
        FilledButton.icon(
          onPressed: trading.emergencyStop ? null : () => _showKillSwitchConfirm(context),
          icon: const Icon(Icons.power_settings_new_rounded),
          label: Text(trading.emergencyStop ? 'Kill switch active' : 'Kill switch'),
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.red,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 18),
            textStyle: AppText.headline,
          ),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Text('Stops all new orders, manual and automatic. Open positions stay protected.',
              style: AppText.caption),
        ),
      ],
    );
  }

  static final _countFmt = NumberFormat.decimalPattern('en_IN');
  static String _count(dynamic v) => _countFmt.format((v as num?) ?? 0);

  static String _title(String s) {
    final w = s.toLowerCase();
    return w.split(' ').map((x) => x.isEmpty ? x : '${x[0].toUpperCase()}${x.substring(1)}').join(' ');
  }

  // ── Strategy card ──────────────────────────────────────────────────────────

  Widget _buildStrategyCard(String key, dynamic weightValue) {
    final isEnabled = (weightValue as num) > 0;
    final meta = _strategyMeta[key] ?? _defaultMeta;
    final accent = isEnabled ? meta['accentColor'] as Color : AppColors.tertiary;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Surface(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  alignment: Alignment.center,
                  decoration: ShapeDecoration(color: accent.withValues(alpha: 0.16), shape: rounded(10)),
                  child: Icon(meta['icon'] as IconData, color: accent, size: 20),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(_title(key.replaceAll('_', ' ')),
                          style: AppText.headline.copyWith(
                              color: isEnabled ? AppColors.label : AppColors.secondary)),
                      Text('${meta['type']} · ${meta['regime']}', style: AppText.caption),
                    ],
                  ),
                ),
                Pill(isEnabled ? 'Weight ${weightValue.toStringAsFixed(2)}' : 'Off',
                    color: isEnabled ? accent : AppColors.red),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              isEnabled
                  ? meta['description'] as String
                  : 'Turned off by the nightly job (low expected value or a cluster of losses).',
              style: AppText.footnote,
            ),
          ],
        ),
      ),
    );
  }

  // ── Shared helpers ─────────────────────────────────────────────────────────

  // ── Automation card ────────────────────────────────────────────────────────

  Widget _buildAutomationCard(BuildContext context, TradingProvider trading) {
    final status = trading.paperStatus;
    final running = trading.autoRunning;
    final known = status.isNotEmpty;
    final accent = running ? AppColors.green : AppColors.orange;

    return Surface(
      padding: const EdgeInsets.fromLTRB(16, 16, 12, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              AnimatedContainer(
                duration: motionDuration(context, 250),
                width: 44,
                height: 44,
                alignment: Alignment.center,
                decoration: ShapeDecoration(color: accent.withValues(alpha: 0.16), shape: rounded(12)),
                child: Icon(running ? Icons.auto_awesome : Icons.pause_rounded, color: accent, size: 24),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(!known ? 'Paper strategies' : (running ? 'Running' : 'Paused'), style: AppText.headline),
                    Text(
                      !known
                          ? 'Connecting…'
                          : running
                              ? 'Strategies can open new paper trades.'
                              : 'No new entries. Open positions still exit on SL, target or end of day.',
                      style: AppText.footnote,
                    ),
                  ],
                ),
              ),
              Switch(
                value: running,
                onChanged: !known || trading.emergencyStop
                    ? null
                    : (v) async {
                        HapticFeedback.selectionClick();
                        final messenger = ScaffoldMessenger.of(context);
                        final res = await trading.setAutomation(v);
                        notify(messenger, res.message, ok: res.ok);
                      },
              ),
            ],
          ),
          if (known) ...[
            const SizedBox(height: 16),
            const Divider(),
            const SizedBox(height: 14),
            Row(
              children: [
                _miniStat('Signals', '${status['signals_emitted_today'] ?? 0}'),
                _miniStat('Positions', '${trading.positions.length}'),
                _miniStat('Candles', _count(status['candles_processed'])),
                _miniStat('Ticks', _count(status['ticks_received'])),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _miniStat(String label, String value) => Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(value, style: AppText.title3.copyWith(fontFeatures: AppText.tabular)),
            ),
            Text(label, style: AppText.caption),
          ],
        ),
      );

  Widget _buildEmergencyBanner(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Surface(
        color: AppColors.red.withValues(alpha: 0.14),
        padding: const EdgeInsets.fromLTRB(14, 8, 8, 8),
        child: Row(
          children: [
            const Icon(Icons.block_rounded, color: AppColors.red),
            const SizedBox(width: 10),
            const Expanded(
              child: Text('Emergency stop is on. All new orders are blocked.', style: AppText.subhead),
            ),
            TextButton(
              onPressed: () async {
                final trading = context.read<TradingProvider>();
                final messenger = ScaffoldMessenger.of(context);
                final res = await trading.clearEmergencyStop();
                notify(messenger, res.message, ok: res.ok);
              },
              child: const Text('Clear'),
            ),
          ],
        ),
      ),
    );
  }

  void _showKillSwitchConfirm(BuildContext context) {
    final trading = context.read<TradingProvider>();
    final messenger = ScaffoldMessenger.of(context);
    final confirmCtrl = TextEditingController();
    bool closeAll = trading.positions.isNotEmpty;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: AppColors.red),
              SizedBox(width: 8),
              Text('Trip the kill switch?'),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Blocks all new manual and automated orders. Open positions keep '
                'their stop-loss, target and end-of-day exits.',
                style: TextStyle(height: 1.4),
              ),
              if (trading.positions.isNotEmpty)
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: closeAll,
                  onChanged: (v) => setState(() => closeAll = v ?? false),
                  title: Text('Also close all ${trading.positions.length} open position(s) at market'),
                ),
              const SizedBox(height: 8),
              TextField(
                controller: confirmCtrl,
                autofocus: true,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(labelText: 'Type KILL to confirm'),
                onChanged: (_) => setState(() {}),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: confirmCtrl.text.trim().toUpperCase() != 'KILL'
                  ? null
                  : () async {
                      Navigator.pop(ctx);
                      HapticFeedback.heavyImpact();
                      final res = await trading.tripEmergencyStop(closeAll: closeAll);
                      notify(messenger, res.message, ok: res.ok, duration: const Duration(seconds: 6));
                    },
              style: FilledButton.styleFrom(backgroundColor: AppColors.red, foregroundColor: Colors.white),
              child: const Text('Trip kill switch'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProgressBar(BuildContext context, String label, double spent, double limit) {
    final progress = limit > 0 ? (spent / limit).clamp(0.0, 1.0) : 0.0;
    // Colour says how close to the limit you are, not which limit it is.
    final color = progress >= 0.9 ? AppColors.red : (progress >= 0.7 ? AppColors.orange : AppColors.accent);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(label, style: AppText.callout)),
            Text.rich(
              TextSpan(children: [
                TextSpan(text: inrWhole(spent), style: AppText.subhead),
                TextSpan(text: ' of ${inrWhole(limit)}', style: AppText.footnote),
              ]),
              style: const TextStyle(fontFeatures: AppText.tabular),
            ),
          ],
        ),
        const SizedBox(height: 8),
        TweenAnimationBuilder<double>(
          tween: Tween(end: progress),
          duration: motionDuration(context, 500),
          curve: motionCurve,
          builder: (_, v, __) => LinearProgressIndicator(
            value: v,
            color: color,
            minHeight: 6,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
      ],
    );
  }
}
